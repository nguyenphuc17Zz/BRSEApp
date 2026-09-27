"""Regression plans: DRAFT -> REVIEWED -> APPROVED, user-edited, run creation.

Audit via core AuditEvent (who/when/what). AI never auto-runs (§42).
"""
import json
import re
from typing import Any, Dict, List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent
from app.qa.models import TestCase
from app.qa.regression_models import (
    ChangeRecord, RegressionPlan, RegressionPlanChange, RegressionPlanItem,
)
from app.qa import execution_engines as X
from app.qa.regression import recommender as RC


async def next_plan_code(db: AsyncSession, project_id: str) -> str:
    res = await db.execute(select(RegressionPlan.plan_code).where(
        RegressionPlan.project_id == project_id))
    max_n = 0
    for (code,) in res.all():
        m = re.search(r"(\d+)$", code or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"RP-{max_n + 1:02d}"


async def audit(db: AsyncSession, event_type: str, details: Dict[str, Any]) -> None:
    db.add(AuditEvent(event_type=f"qa_regression:{event_type}",
                      details_json=json.dumps(details, ensure_ascii=False, default=str)))
    await db.flush()


async def plan_change_ids(db: AsyncSession, plan_id: str) -> List[str]:
    links = (await db.execute(select(RegressionPlanChange).where(
        RegressionPlanChange.plan_id == plan_id))).scalars().all()
    return [l.change_id for l in links]


async def create_plan(
    db: AsyncSession, project_id: str, change_ids: List[str],
    release_tag: Optional[str] = None,
    time_budget_min: Optional[int] = None,
    created_by: str = "user",
    preferred_provider: Optional[str] = None, model: Optional[str] = None,
) -> RegressionPlan:
    for cid in change_ids:
        ch = (await db.execute(select(ChangeRecord).where(ChangeRecord.id == cid))).scalars().first()
        if not ch or ch.project_id != project_id:
            raise ValueError(f"Change not found in project: {cid}")
    rec = await RC.recommend_for_changes(db, change_ids, preferred_provider, model)
    boxed = RC.apply_timebox(rec["items"], time_budget_min)
    plan = RegressionPlan(
        project_id=project_id, plan_code=await next_plan_code(db, project_id),
        release_tag=release_tag, status="DRAFT",
        time_budget_min=time_budget_min, created_by=created_by)
    db.add(plan)
    await db.flush()
    for cid in change_ids:
        db.add(RegressionPlanChange(plan_id=plan.id, change_id=cid))
    for it in boxed["items"]:
        db.add(RegressionPlanItem(
            plan_id=plan.id, test_case_id=it["test_case_id"], tier=it["tier"],
            reason="; ".join(it["reasons"])[:2000],
            relationship_path=json.dumps(it["relationship_path"], ensure_ascii=False),
            risk=it["risk"], impact_confidence=it["impact_confidence"],
            priority_rank=it["priority_rank"], added_by="ai", status="PENDING"))
    for ex in boxed["excluded"]:
        db.add(RegressionPlanItem(
            plan_id=plan.id, test_case_id=ex["test_case_id"], tier="EXCLUDED",
            reason=f"Excluded by time-box ({boxed.get('budget_minutes')} min): "
                   + "; ".join(ex["reasons"])[:1500],
            relationship_path=json.dumps(ex["relationship_path"], ensure_ascii=False),
            risk=ex["risk"], impact_confidence=ex["impact_confidence"],
            priority_rank=ex["priority_rank"], added_by="ai", status="SKIPPED"))
    await db.flush()
    await audit(db, "plan_created",
                {"plan_id": plan.id, "plan_code": plan.plan_code,
                 "changes": change_ids, "by": created_by,
                 "residual_risk": boxed.get("residual_risk", [])})
    await db.commit()
    await db.refresh(plan)
    return plan


async def set_plan_status(db: AsyncSession, plan_id: str, status: str,
                          changed_by: str = "user") -> RegressionPlan:
    status = status.upper()
    if status not in ("DRAFT", "REVIEWED", "APPROVED"):
        raise ValueError("Invalid plan status")
    plan = (await db.execute(select(RegressionPlan).where(
        RegressionPlan.id == plan_id))).scalars().first()
    if not plan:
        raise ValueError("Plan not found")
    order = {"DRAFT": 0, "REVIEWED": 1, "APPROVED": 2}
    if order[status] < order[plan.status]:
        raise ValueError(f"Cannot move plan backwards ({plan.status} -> {status})")
    old = plan.status
    plan.status = status
    await db.flush()
    await audit(db, "plan_status", {"plan_id": plan.id, "old": old,
                                    "new": status, "by": changed_by})
    await db.commit()
    await db.refresh(plan)
    return plan


async def add_plan_item(db: AsyncSession, plan_id: str, test_case_id: str,
                        tier: str = "RECOMMENDED", reason: str = "",
                        changed_by: str = "user") -> RegressionPlanItem:
    plan = (await db.execute(select(RegressionPlan).where(
        RegressionPlan.id == plan_id))).scalars().first()
    if not plan:
        raise ValueError("Plan not found")
    if plan.status == "APPROVED":
        raise ValueError("Plan already APPROVED — create a new plan to change scope")
    tc = (await db.execute(select(TestCase).where(TestCase.id == test_case_id))).scalars().first()
    if not tc:
        raise ValueError("Test case not found")
    exists = (await db.execute(select(RegressionPlanItem).where(
        RegressionPlanItem.plan_id == plan_id,
        RegressionPlanItem.test_case_id == test_case_id,
        RegressionPlanItem.tier != "EXCLUDED"))).scalars().first()
    if exists:
        raise ValueError("Test case already in plan")
    if tier.upper() not in ("MUST_RUN", "RECOMMENDED", "OPTIONAL"):
        raise ValueError("Invalid tier")
    max_rank = (await db.execute(select(func.max(RegressionPlanItem.priority_rank)).where(
        RegressionPlanItem.plan_id == plan_id))).scalar() or 0
    item = RegressionPlanItem(plan_id=plan_id, test_case_id=test_case_id,
                              tier=tier.upper(), reason=reason[:2000] or "Added by user",
                              relationship_path="[]", risk="MEDIUM",
                              impact_confidence="High", priority_rank=max_rank + 1,
                              added_by="user", status="PENDING")
    db.add(item)
    await db.flush()
    await audit(db, "plan_item_added",
                {"plan_id": plan_id, "test_case_id": test_case_id,
                 "tier": tier, "by": changed_by})
    await db.commit()
    await db.refresh(item)
    return item


async def remove_plan_item(db: AsyncSession, item_id: str,
                           changed_by: str = "user") -> None:
    item = (await db.execute(select(RegressionPlanItem).where(
        RegressionPlanItem.id == item_id))).scalars().first()
    if not item:
        raise ValueError("Plan item not found")
    plan = (await db.execute(select(RegressionPlan).where(
        RegressionPlan.id == item.plan_id))).scalars().first()
    if plan and plan.status == "APPROVED":
        raise ValueError("Plan already APPROVED — create a new plan to change scope")
    await db.delete(item)
    await db.flush()
    await audit(db, "plan_item_removed",
                {"plan_id": item.plan_id, "test_case_id": item.test_case_id, "by": changed_by})
    await db.commit()


async def approve_and_create_run(
    db: AsyncSession, plan_id: str, payload: Dict[str, Any],
    changed_by: str = "user",
) -> Dict[str, Any]:
    """Approves the plan and creates a REGRESSION TestRun (reuse Phase 2)."""
    plan = (await db.execute(select(RegressionPlan).where(
        RegressionPlan.id == plan_id))).scalars().first()
    if not plan:
        raise ValueError("Plan not found")
    if plan.status != "APPROVED":
        plan.status = "APPROVED"
        await db.flush()
        await audit(db, "plan_status", {"plan_id": plan.id, "old": "REVIEWED",
                                        "new": "APPROVED", "by": changed_by})
    items = (await db.execute(select(RegressionPlanItem).where(
        RegressionPlanItem.plan_id == plan_id,
        RegressionPlanItem.tier.in_(["MUST_RUN", "RECOMMENDED", "OPTIONAL"]),
        RegressionPlanItem.status == "PENDING").order_by(
        RegressionPlanItem.priority_rank))).scalars().all()
    if not items:
        raise ValueError("No pending items in plan")
    changes = (await db.execute(select(ChangeRecord).where(
        ChangeRecord.id.in_(await plan_change_ids(db, plan.id))
    ))).scalars().all() if await plan_change_ids(db, plan.id) else []
    codes = ",".join(c.change_code for c in changes) or plan.plan_code
    run = await X.create_run(db, plan.project_id, {
        "name": payload.get("name") or f"Regression {plan.plan_code} ({codes})",
        "version_build": payload.get("version_build") or "",
        "environment": payload.get("environment") or "",
        "tester": payload.get("tester") or changed_by,
        "notes": f"Regression plan {plan.plan_code}",
        "scope": {"origin": "regression_plan", "plan_id": plan.id,
                  "change_ids": await plan_change_ids(db, plan.id)}})
    run.run_type = "REGRESSION"
    await db.flush()
    cases = []
    for it in items:
        tc = (await db.execute(select(TestCase).where(TestCase.id == it.test_case_id))).scalars().first()
        if tc and tc.status != "REJECTED":
            cases.append(tc)
    added = await X.add_cases_to_run(db, run, cases)
    for it in items:
        it.status = "IN_RUN"
    await db.flush()
    plan.test_run_id = run.id
    await db.flush()
    await audit(db, "plan_run_created",
                {"plan_id": plan.id, "run_id": run.id, "added": added, "by": changed_by})
    await db.commit()
    await db.refresh(run)
    return {"plan_id": plan.id, "test_run_id": run.id,
            "run_code": run.run_code, "added": added}


async def plan_summary(db: AsyncSession, plan_id: str) -> Dict[str, Any]:
    """Execution summary + change coverage + gaps (§30-32). Evidence only, no verdict."""
    from app.qa.execution_models import TestExecution
    plan = (await db.execute(select(RegressionPlan).where(
        RegressionPlan.id == plan_id))).scalars().first()
    if not plan:
        raise ValueError("Plan not found")
    items = (await db.execute(select(RegressionPlanItem).where(
        RegressionPlanItem.plan_id == plan_id))).scalars().all()
    recommended = [i for i in items if i.tier != "EXCLUDED"]
    excluded = [i for i in items if i.tier == "EXCLUDED"]
    executed = passed = failed = blocked = skipped = not_run = 0
    critical_failures = []
    if plan.test_run_id:
        for it in recommended:
            ex = (await db.execute(select(TestExecution).where(
                TestExecution.test_run_id == plan.test_run_id,
                TestExecution.test_case_id == it.test_case_id).order_by(
                TestExecution.attempt_no.desc()).limit(1))).scalars().first()
            st = ex.status if ex else "NOT_RUN"
            if st == "PASS":
                passed += 1
                executed += 1
            elif st == "FAIL":
                failed += 1
                executed += 1
                tc = (await db.execute(select(TestCase).where(
                    TestCase.id == it.test_case_id))).scalars().first()
                if (tc and tc.priority in ("CRITICAL", "HIGH")) or it.risk in ("CRITICAL", "HIGH"):
                    critical_failures.append({"tc_code": tc.tc_code if tc else "",
                                              "title": tc.title if tc else ""})
            elif st == "BLOCKED":
                blocked += 1
                executed += 1
            elif st == "SKIPPED":
                skipped += 1
                executed += 1
            else:
                not_run += 1
    # change coverage: affected vs selected vs executed
    changes = (await db.execute(select(ChangeRecord).where(
        ChangeRecord.id.in_(await plan_change_ids(db, plan.id))
    ))).scalars().all() if await plan_change_ids(db, plan.id) else []
    return {"plan_id": plan.id, "plan_code": plan.plan_code, "status": plan.status,
            "recommended": len(recommended), "executed": executed, "passed": passed,
            "failed": failed, "blocked": blocked, "skipped": skipped, "not_run": not_run,
            "critical_failures": critical_failures,
            "affected_changes": [{"code": c.change_code, "summary": (c.change_summary or "")[:200]} for c in changes],
            "excluded": [{"test_case_id": e.test_case_id, "reason": e.reason[:200]} for e in excluded]}
