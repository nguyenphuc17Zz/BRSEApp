"""QA Phase 5 REST API: changes, versions, spec diff, regression plans, coverage."""
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.intelligence.models import WorkItem
from app.qa.models import TestCase
from app.qa.regression_models import (
    ChangeRecord, RequirementVersion, RegressionPlan, RegressionPlanChange,
    RegressionPlanItem,
)
from app.qa import schemas as S
from app.qa import engines as E1
from app.qa.router import _ts
from app.qa.regression import change_engine as CE
from app.qa.regression import diff_adapter as DA
from app.qa.regression import impact_graph as IG
from app.qa.regression import risk_engine as RK
from app.qa.regression import plan_engine as PE

router = APIRouter(prefix="/api/qa", tags=["QA Regression Intelligence"])


def _jl(text: str, default):
    try:
        return json.loads(text or "") if (text or "").strip() else default
    except Exception:
        return default


def ser_change(c: ChangeRecord) -> dict:
    return {"id": c.id, "project_id": c.project_id, "change_code": c.change_code or "",
            "source": c.source, "requirement_id": c.requirement_id,
            "decision_id": c.decision_id, "bug_id": c.bug_id,
            "old_snapshot": _jl(c.old_snapshot_json, {}),
            "new_snapshot": _jl(c.new_snapshot_json, {}),
            "change_summary": c.change_summary or "",
            "business_summary": c.business_summary or "",
            "categories": _jl(c.categories_json, []),
            "risk_level": c.risk_level, "risk_reasons": _jl(c.risk_reasons_json, []),
            "status": c.status, "created_by": c.created_by,
            "created_at": _ts(c.created_at)}


async def ser_plan(db: AsyncSession, p: RegressionPlan) -> dict:
    from app.qa.regression.plan_engine import plan_change_ids
    items = (await db.execute(select(RegressionPlanItem).where(
        RegressionPlanItem.plan_id == p.id))).scalars().all()
    codes = []
    for cid in await plan_change_ids(db, p.id):
        ch = (await db.execute(select(ChangeRecord).where(
            ChangeRecord.id == cid))).scalars().first()
        if ch:
            codes.append(ch.change_code)
    return {"id": p.id, "project_id": p.project_id, "plan_code": p.plan_code or "",
            "release_tag": p.release_tag, "status": p.status,
            "time_budget_min": p.time_budget_min, "test_run_id": p.test_run_id,
            "change_codes": codes, "item_count": len(items),
            "must_count": sum(1 for i in items if i.tier == "MUST_RUN"),
            "created_by": p.created_by, "created_at": _ts(p.created_at),
            "updated_at": _ts(p.updated_at)}


async def ser_item(db: AsyncSession, it: RegressionPlanItem) -> dict:
    tc = (await db.execute(select(TestCase).where(TestCase.id == it.test_case_id))).scalars().first()
    return {"id": it.id, "test_case_id": it.test_case_id,
            "tc_code": tc.tc_code if tc else "", "title": tc.title if tc else "",
            "tier": it.tier, "reason": it.reason or "",
            "relationship_path": _jl(it.relationship_path, []),
            "risk": it.risk, "impact_confidence": it.impact_confidence,
            "priority_rank": it.priority_rank, "added_by": it.added_by,
            "status": it.status}


# ---------- Changes ----------
@router.post("/changes", response_model=S.ChangeResponse)
async def create_change(project_id: str, payload: S.ChangeCreate,
                        changed_by: str = "user", db: AsyncSession = Depends(get_db)):
    try:
        change = await CE.create_change(db, project_id, payload.model_dump(), changed_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ser_change(change)


@router.get("/changes", response_model=List[S.ChangeResponse])
async def list_changes(project_id: str, source: Optional[str] = None,
                       status: Optional[str] = None, search: Optional[str] = None,
                       db: AsyncSession = Depends(get_db)):
    stmt = select(ChangeRecord).where(
        ChangeRecord.project_id == project_id).order_by(desc(ChangeRecord.created_at))
    if source:
        stmt = stmt.where(ChangeRecord.source == source.lower())
    if status:
        stmt = stmt.where(ChangeRecord.status == status.upper())
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(ChangeRecord.change_code.like(like),
                             ChangeRecord.change_summary.like(like)))
    rows = (await db.execute(stmt.limit(200))).scalars().all()
    return [ser_change(c) for c in rows]


@router.get("/changes/suggest")
async def suggest_changes(project_id: str, db: AsyncSession = Depends(get_db)):
    return await CE.suggest_changes(db, project_id)


@router.get("/changes/{change_id}")
async def change_detail(change_id: str, db: AsyncSession = Depends(get_db)):
    c = (await db.execute(select(ChangeRecord).where(
        ChangeRecord.id == change_id))).scalars().first()
    if not c:
        raise HTTPException(status_code=404, detail="Change not found")
    out = ser_change(c)
    # linked plans
    links = (await db.execute(select(RegressionPlanChange).where(
        RegressionPlanChange.change_id == change_id))).scalars().all()
    out["plan_ids"] = [l.plan_id for l in links]
    return out


@router.post("/changes/{change_id}/analyze")
async def analyze_change(change_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    """Full analysis: diff aspects + impact graph + risk + outdated flags. Sets ANALYZED."""
    c = (await db.execute(select(ChangeRecord).where(
        ChangeRecord.id == change_id))).scalars().first()
    if not c:
        raise HTTPException(status_code=404, detail="Change not found")
    prov = (payload or {}).get("preferred_provider")
    model = (payload or {}).get("model")
    before_after = await DA.requirement_before_after(db, change_id, prov, model)
    impact = await IG.build_impact(db, change_id, prov, model)
    # risk per seed requirement -> change-level max
    all_reasons: List[str] = []
    risks = []
    for rid in impact["seed_requirements"]:
        r = await RK.assess_requirement_risk(db, c.project_id, rid, changed=True)
        risks.append(r["risk"])
        all_reasons.extend([f"[{rid[:6]}] {x}" for x in r["reasons"]])
    c.risk_level = RK.max_risk(risks) if risks else "MEDIUM"
    c.risk_reasons_json = json.dumps(all_reasons[:20], ensure_ascii=False)
    c.status = "ANALYZED"
    flags = await RC_flag(db, change_id)
    await db.commit()
    await db.refresh(c)
    return {"change": ser_change(c), "before_after": before_after,
            "impact": impact, "outdated_flags": flags}


async def RC_flag(db: AsyncSession, change_id: str) -> dict:
    from app.qa.regression import recommender as _RC
    return await _RC.flag_outdated(db, change_id)


# ---------- Requirement versions (§43) ----------
@router.get("/requirements/{requirement_id}/versions")
async def requirement_versions(requirement_id: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(RequirementVersion).where(
        RequirementVersion.requirement_id == requirement_id).order_by(
        RequirementVersion.version_no))).scalars().all()
    return [{"id": v.id, "version_no": v.version_no, "title": v.title,
             "description": v.description,
             "acceptance_criteria": _jl(v.ac_snapshot_json, []),
             "source": v.source, "created_by": v.created_by,
             "created_at": _ts(v.created_at)} for v in rows]


# ---------- Spec diff (§5) ----------
@router.post("/specs:diff")
async def spec_diff(payload: dict, db: AsyncSession = Depends(get_db)):
    old = payload.get("old_text") or ""
    new = payload.get("new_text") or ""
    if not old or not new:
        raise HTTPException(status_code=400, detail="old_text and new_text are required.")
    return await DA.spec_versions_diff(
        old, new, payload.get("label") or "Spec v1 vs v2",
        payload.get("preferred_provider"), payload.get("model"))


# ---------- Regression plans ----------
@router.post("/plans", response_model=S.RegressionPlanResponse)
async def create_plan(project_id: str, payload: S.RegressionPlanCreate,
                      created_by: str = "user", db: AsyncSession = Depends(get_db)):
    try:
        plan = await PE.create_plan(db, project_id, payload.change_ids,
                                    payload.release_tag, payload.time_budget_min,
                                    created_by, payload.preferred_provider,
                                    payload.model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await ser_plan(db, plan)


@router.get("/plans", response_model=List[S.RegressionPlanResponse])
async def list_plans(project_id: str, status: Optional[str] = None,
                     db: AsyncSession = Depends(get_db)):
    stmt = select(RegressionPlan).where(
        RegressionPlan.project_id == project_id).order_by(desc(RegressionPlan.created_at))
    if status:
        stmt = stmt.where(RegressionPlan.status == status.upper())
    rows = (await db.execute(stmt.limit(200))).scalars().all()
    return [await ser_plan(db, p) for p in rows]


@router.get("/plans/{plan_id}")
async def plan_detail(plan_id: str, db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(RegressionPlan).where(
        RegressionPlan.id == plan_id))).scalars().first()
    if not p:
        raise HTTPException(status_code=404, detail="Plan not found")
    out = await ser_plan(db, p)
    items = (await db.execute(select(RegressionPlanItem).where(
        RegressionPlanItem.plan_id == plan_id).order_by(
        RegressionPlanItem.priority_rank))).scalars().all()
    out["items"] = [await ser_item(db, it) for it in items]
    from app.qa.regression.plan_engine import plan_change_ids as _pcids
    _cids = await _pcids(db, plan_id)
    changes = (await db.execute(select(ChangeRecord).where(
        ChangeRecord.id.in_(_cids)))).scalars().all() if _cids else []
    out["changes"] = [ser_change(c) for c in changes]
    return out


@router.patch("/plans/{plan_id}", response_model=S.RegressionPlanResponse)
async def update_plan(plan_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    try:
        plan = await PE.set_plan_status(db, plan_id, payload.get("status") or "",
                                        (payload or {}).get("changed_by") or "user")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await ser_plan(db, plan)


@router.post("/plans/{plan_id}/items", response_model=S.RegressionPlanItemResponse)
async def add_item(plan_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    try:
        item = await PE.add_plan_item(db, plan_id, payload.get("test_case_id") or "",
                                      payload.get("tier") or "RECOMMENDED",
                                      payload.get("reason") or "",
                                      (payload or {}).get("changed_by") or "user")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await ser_item(db, item)


@router.delete("/plans/items/{item_id}")
async def remove_item(item_id: str, changed_by: str = "user",
                      db: AsyncSession = Depends(get_db)):
    try:
        await PE.remove_plan_item(db, item_id, changed_by)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "deleted", "id": item_id}


@router.post("/plans/{plan_id}/run")
async def run_plan(plan_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    """Approves (if needed) and creates a REGRESSION TestRun with plan cases."""
    try:
        return await PE.approve_and_create_run(db, plan_id, payload or {},
                                               (payload or {}).get("changed_by") or "user")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/plans/{plan_id}/summary")
async def plan_summary(plan_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await PE.plan_summary(db, plan_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---------- Change coverage (§31-32) ----------
@router.get("/change-coverage")
async def change_coverage(plan_id: Optional[str] = None,
                          change_ids: Optional[str] = None,
                          db: AsyncSession = Depends(get_db)):
    """Affected vs selected vs executed vs pass/fail + not-covered gaps."""
    from app.qa.execution_models import TestExecution
    from app.qa.regression import recommender as _RC
    cids: List[str] = []
    plan = None
    if plan_id:
        plan = (await db.execute(select(RegressionPlan).where(
            RegressionPlan.id == plan_id))).scalars().first()
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        links = (await db.execute(select(RegressionPlanChange).where(
            RegressionPlanChange.plan_id == plan_id))).scalars().all()
        cids = [l.change_id for l in links]
    elif change_ids:
        cids = [c.strip() for c in change_ids.split(",") if c.strip()]
    if not cids:
        raise HTTPException(status_code=400, detail="plan_id or change_ids required.")
    affected_reqs: set = set()
    affected_cases: Dict[str, dict] = {}
    for cid in cids:
        impact = await IG.build_impact(db, cid)
        affected_reqs.update(impact["seed_requirements"])
        for c in impact["cases"]:
            affected_cases[c["id"]] = c
    selected: set = set()
    if plan:
        items = (await db.execute(select(RegressionPlanItem).where(
            RegressionPlanItem.plan_id == plan.id,
            RegressionPlanItem.tier != "EXCLUDED"))).scalars().all()
        selected = {i.test_case_id for i in items}
    else:
        rec = await _RC.recommend_for_changes(db, cids)
        selected = {i["test_case_id"] for i in rec["items"]}
    executed = passed = failed = 0
    run_id = plan.test_run_id if plan else None
    per_case = []
    for tcid in affected_cases:
        stmt = select(TestExecution).where(TestExecution.test_case_id == tcid)
        if run_id:
            stmt = stmt.where(TestExecution.test_run_id == run_id)
        ex = (await db.execute(stmt.order_by(TestExecution.attempt_no.desc()).limit(1))
              ).scalars().first()
        st = ex.status if ex else "NOT_RUN"
        if st in ("PASS", "FAIL", "BLOCKED", "SKIPPED"):
            executed += 1
        if st == "PASS":
            passed += 1
        if st == "FAIL":
            failed += 1
        tc = (await db.execute(select(TestCase).where(TestCase.id == tcid))).scalars().first()
        per_case.append({"test_case_id": tcid,
                         "tc_code": tc.tc_code if tc else "",
                         "title": tc.title if tc else "",
                         "selected": tcid in selected, "status": st})
    not_covered = [c for c in per_case if c["tc_code"] and not c["selected"]]
    unselected_run = [c for c in per_case if c["selected"] and c["status"] == "NOT_RUN"]
    return {"affected_requirements": len(affected_reqs),
            "affected_cases": len(affected_cases),
            "selected": len(selected), "executed": executed,
            "passed": passed, "failed": failed,
            "not_covered": not_covered, "selected_not_run": unselected_run,
            "cases": per_case}


# ---------- Phase 6 hook: data rules related to a plan's changes (§57) ----------
@router.get("/plans/{plan_id}/data-suggestions")
async def plan_data_suggestions(plan_id: str, db: AsyncSession = Depends(get_db)):
    """Recommends approved DATA rules + jobs touching the plan's affected requirements."""
    from app.qa.data_models import DataQualityRule, DataQaJob
    from app.qa.regression.plan_engine import plan_change_ids
    from app.qa.regression import impact_graph as _IG
    plan = (await db.execute(select(RegressionPlan).where(
        RegressionPlan.id == plan_id))).scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    req_ids: set = set()
    for cid in await plan_change_ids(db, plan_id):
        try:
            impact = await _IG.build_impact(db, cid)
            req_ids.update(impact.get("seed_requirements", []))
        except Exception:
            continue
    suggestions = []
    if req_ids:
        rules = (await db.execute(select(DataQualityRule).where(
            DataQualityRule.requirement_id.in_(list(req_ids)),
            DataQualityRule.status == "APPROVED"))).scalars().all()
        for r in rules:
            job_name = ""
            if r.job_id:
                job = (await db.execute(select(DataQaJob).where(
                    DataQaJob.id == r.job_id))).scalars().first()
                job_name = f"{job.job_code} {job.name}" if job else ""
            suggestions.append({"rule_id": r.id, "rule_type": r.rule_type,
                                "job_id": r.job_id, "job_name": job_name,
                                "test_case_id": r.test_case_id,
                                "reason": "Approved DATA rule on affected requirement"})
    return {"suggestions": suggestions}
