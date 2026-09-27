"""QA Phase 4 REST API: UI scripts, mappings, pages, background runs, UI coverage."""
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.intelligence.models import WorkItem
from app.qa.models import TestCase
from app.qa.ui_models import (
    UIAutomationScript, UIAutomationScriptHistory, UIElementMapping, UIPageKnowledge,
)
from app.qa.api_models import APITestConfig
from app.qa.execution_models import TestExecution
from app.qa import schemas as S
from app.qa import engines as E1
from app.qa import execution_engines as X
from app.qa.router import _ts
from app.qa.ui_testing import locator_policy as LP
from app.qa.ui_testing import script_generator as SG
from app.qa.ui_testing import playwright_runner as PR
from app.qa.ui_testing import failure_analyzer as FA

router = APIRouter(prefix="/api/qa", tags=["QA UI Automation"])

VALID_SCRIPT_STATUS = {"NOT_GENERATED", "GENERATED", "REVIEW_REQUIRED",
                       "APPROVED", "NEEDS_UPDATE", "DISABLED"}


def _jloads(text: str, default):
    try:
        return json.loads(text or "") if (text or "").strip() else default
    except Exception:
        return default


async def test_type_of(db: AsyncSession, test_case_id: str) -> str:
    ui = (await db.execute(select(UIAutomationScript.test_case_id).where(
        UIAutomationScript.test_case_id == test_case_id))).scalars().first()
    if ui:
        return "WEB_UI"
    api = (await db.execute(select(APITestConfig.test_case_id).where(
        APITestConfig.test_case_id == test_case_id))).scalars().first()
    if api:
        return "API"
    return "MANUAL"


def ser_script(script: UIAutomationScript, tc_code: str = "") -> dict:
    flow = _jloads(script.flow_json, [])
    return {"test_case_id": script.test_case_id, "tc_code": tc_code,
            "flow": flow, "script_text": script.script_text or "",
            "script_version": script.script_version, "status": script.status,
            "playwright_version": script.playwright_version or "",
            "timeout_s": script.timeout_s, "is_smoke": script.is_smoke,
            "manual_preferred": script.manual_preferred,
            "manual_preferred_reason": script.manual_preferred_reason,
            "flaky_flag": script.flaky_flag,
            "needs_mapping": any(s.get("selector_required") for s in flow),
            "policy_problems": [], "test_type": "WEB_UI",
            "updated_by": script.updated_by, "update_reason": script.update_reason,
            "updated_at": _ts(script.updated_at)}


# ---------- Scripts ----------
@router.post("/ui-scripts:generate")
async def generate_script(payload: dict, db: AsyncSession = Depends(get_db)):
    if not payload.get("test_case_id"):
        raise HTTPException(status_code=400, detail="test_case_id is required.")
    try:
        return await SG.generate_ui_flow(
            db, payload["test_case_id"], payload.get("preferred_provider"),
            payload.get("model"), payload.get("changed_by") or "user")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ui-scripts")
async def list_scripts(project_id: str, status: Optional[str] = None,
                       smoke: Optional[bool] = None, flaky: Optional[bool] = None,
                       search: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(UIAutomationScript).join(
        TestCase, TestCase.id == UIAutomationScript.test_case_id).where(
        TestCase.project_id == project_id).order_by(desc(TestCase.updated_at))
    if status:
        stmt = stmt.where(UIAutomationScript.status == status.upper())
    if smoke is not None:
        stmt = stmt.where(UIAutomationScript.is_smoke == smoke)
    if flaky is not None:
        stmt = stmt.where(UIAutomationScript.flaky_flag == flaky)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(TestCase.title.like(like), TestCase.tc_code.like(like)))
    scripts = (await db.execute(stmt.limit(300))).scalars().all()
    out = []
    for s in scripts:
        tc = (await db.execute(select(TestCase).where(TestCase.id == s.test_case_id))).scalars().first()
        last_ex = (await db.execute(select(TestExecution).where(
            TestExecution.test_case_id == s.test_case_id).order_by(
            desc(TestExecution.updated_at)).limit(1))).scalars().first()
        d = ser_script(s, tc.tc_code if tc else "")
        d["title"] = tc.title if tc else ""
        d["requirement_id"] = tc.requirement_id if tc else None
        d["last_result"] = last_ex.status if last_ex else None
        out.append(d)
    return out


@router.get("/ui-scripts/{case_id}")
async def get_script(case_id: str, db: AsyncSession = Depends(get_db)):
    script = (await db.execute(select(UIAutomationScript).where(
        UIAutomationScript.test_case_id == case_id))).scalars().first()
    if not script:
        raise HTTPException(status_code=404, detail="No automation script (NOT_GENERATED).")
    tc = (await db.execute(select(TestCase).where(TestCase.id == case_id))).scalars().first()
    req = await E1.get_requirement(db, tc.requirement_id) if tc and tc.requirement_id else None
    hist = (await db.execute(select(UIAutomationScriptHistory).where(
        UIAutomationScriptHistory.test_case_id == case_id).order_by(
        desc(UIAutomationScriptHistory.version)).limit(20))).scalars().all()
    flaky = await FA.detect_flaky(db, case_id)
    d = ser_script(script, tc.tc_code if tc else "")
    d["title"] = tc.title if tc else ""
    d["requirement"] = {"id": req.id, "req_code": getattr(req, "req_code", None),
                        "title": req.title} if req else None
    d["history"] = [{"id": h.id, "version": h.version, "reason": h.reason,
                     "changed_by": h.changed_by, "created_at": _ts(h.created_at)} for h in hist]
    d["flaky"] = flaky
    if script.flaky_flag != flaky["flaky"]:
        script.flaky_flag = flaky["flaky"]
        await db.commit()
    return d


@router.patch("/ui-scripts/{case_id}")
async def update_script(case_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    script = (await db.execute(select(UIAutomationScript).where(
        UIAutomationScript.test_case_id == case_id))).scalars().first()
    if not script:
        raise HTTPException(status_code=404, detail="No automation script.")
    changed_by = payload.get("changed_by") or "user"
    if payload.get("status"):
        st = payload["status"].upper()
        if st not in VALID_SCRIPT_STATUS:
            raise HTTPException(status_code=400, detail="Invalid status.")
        if st == "APPROVED":
            flow = _jloads(script.flow_json, [])
            if any(s.get("selector_required") for s in flow):
                raise HTTPException(status_code=400, detail="Cannot approve: steps still Selector Required.")
            ok, problems = LP.validate_flow(flow)
            if not ok:
                raise HTTPException(status_code=400, detail=f"Policy violations: {problems[:3]}")
        script.status = st
        script.updated_by = changed_by
        script.update_reason = payload.get("reason") or f"status -> {st}"
    for flag in ("is_smoke", "manual_preferred"):
        if flag in payload:
            setattr(script, flag, bool(payload[flag]))
    if payload.get("manual_preferred_reason") is not None:
        script.manual_preferred_reason = payload["manual_preferred_reason"]
    if payload.get("timeout_s"):
        script.timeout_s = max(30, min(int(payload["timeout_s"]), 1200))
    # human-edited flow: version it
    if isinstance(payload.get("flow"), list):
        ok, problems = LP.validate_flow(payload["flow"])
        if not ok:
            raise HTTPException(status_code=400, detail=f"Policy violations: {problems[:3]}")
        script.script_version = (script.script_version or 0) + 1
        script.flow_json = json.dumps(payload["flow"], ensure_ascii=False)
        script.script_text = LP.render_flow_as_python(payload["flow"])
        script.updated_by = changed_by
        script.update_reason = payload.get("reason") or "human edited flow"
        db.add(UIAutomationScriptHistory(
            test_case_id=case_id, version=script.script_version,
            script_text=script.script_text, flow_json=script.flow_json,
            reason=script.update_reason, changed_by=changed_by))
    await db.commit()
    await db.refresh(script)
    tc = (await db.execute(select(TestCase).where(TestCase.id == case_id))).scalars().first()
    return ser_script(script, tc.tc_code if tc else "")


# ---------- Mappings (§7: reuse across cases) ----------
@router.get("/ui-mappings")
async def list_mappings(project_id: str, page_name: Optional[str] = None,
                        status: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(UIElementMapping).where(
        UIElementMapping.project_id == project_id).order_by(
        UIElementMapping.page_name, UIElementMapping.element_name)
    if page_name:
        stmt = stmt.where(UIElementMapping.page_name == page_name)
    if status:
        stmt = stmt.where(UIElementMapping.status == status.upper())
    rows = (await db.execute(stmt.limit(500))).scalars().all()
    return [{"id": m.id, "project_id": m.project_id, "page_name": m.page_name,
             "element_name": m.element_name, "locator": _jloads(m.locator_json, {}),
             "fallback": _jloads(m.fallback_json, {}) if m.fallback_json else None,
             "status": m.status, "used_count": m.used_count,
             "created_at": _ts(m.created_at), "updated_at": _ts(m.updated_at)} for m in rows]


@router.post("/ui-mappings")
async def create_mapping(project_id: str, payload: S.UIElementMappingCreate,
                         db: AsyncSession = Depends(get_db)):
    loc = payload.locator or {}
    problems = LP.validate_locator(loc.get("strategy", ""), loc.get("value", ""))
    if problems:
        raise HTTPException(status_code=400, detail=f"Locator policy: {problems}")
    m = UIElementMapping(project_id=project_id, page_name=payload.page_name[:150],
                         element_name=payload.element_name[:150],
                         locator_json=json.dumps(loc, ensure_ascii=False),
                         fallback_json=json.dumps(payload.fallback, ensure_ascii=False) if payload.fallback else None)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return {"id": m.id, "project_id": m.project_id, "page_name": m.page_name,
            "element_name": m.element_name, "locator": loc,
            "fallback": payload.fallback, "status": m.status, "used_count": 0,
            "created_at": _ts(m.created_at), "updated_at": _ts(m.updated_at)}


@router.patch("/ui-mappings/{mapping_id}")
async def update_mapping(mapping_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    m = (await db.execute(select(UIElementMapping).where(
        UIElementMapping.id == mapping_id))).scalars().first()
    if not m:
        raise HTTPException(status_code=404, detail="Mapping not found")
    if isinstance(payload.get("locator"), dict):
        problems = LP.validate_locator(payload["locator"].get("strategy", ""),
                                       payload["locator"].get("value", ""))
        if problems:
            raise HTTPException(status_code=400, detail=f"Locator policy: {problems}")
        m.locator_json = json.dumps(payload["locator"], ensure_ascii=False)
        m.status = "ACTIVE"  # re-approved locator clears NEEDS_REVIEW
    if payload.get("status") in ("ACTIVE", "NEEDS_REVIEW"):
        m.status = payload["status"]
    if payload.get("element_name"):
        m.element_name = payload["element_name"][:150]
    await db.commit()
    return {"id": m.id, "status": m.status}


@router.delete("/ui-mappings/{mapping_id}")
async def delete_mapping(mapping_id: str, db: AsyncSession = Depends(get_db)):
    m = (await db.execute(select(UIElementMapping).where(
        UIElementMapping.id == mapping_id))).scalars().first()
    if not m:
        raise HTTPException(status_code=404, detail="Mapping not found")
    await db.delete(m)
    await db.commit()
    return {"status": "deleted", "id": mapping_id}


# ---------- Pages (§8) ----------
@router.get("/ui-pages")
async def list_pages(project_id: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(UIPageKnowledge).where(
        UIPageKnowledge.project_id == project_id).order_by(UIPageKnowledge.page_name)
    )).scalars().all()
    out = []
    for p in rows:
        count = (await db.execute(select(func.count(UIElementMapping.id)).where(
            UIElementMapping.project_id == project_id,
            UIElementMapping.page_name == p.page_name))).scalar() or 0
        out.append({"id": p.id, "project_id": p.project_id, "page_name": p.page_name,
                    "url_path": p.url_path, "description": p.description,
                    "common_actions": _jloads(p.common_actions_json, []),
                    "notes": p.notes, "element_count": count,
                    "created_at": _ts(p.created_at), "updated_at": _ts(p.updated_at)})
    return out


@router.post("/ui-pages")
async def create_page(project_id: str, payload: S.UIPageCreate, db: AsyncSession = Depends(get_db)):
    p = UIPageKnowledge(project_id=project_id, page_name=payload.page_name[:150],
                        url_path=payload.url_path[:500], description=payload.description,
                        common_actions_json=json.dumps(payload.common_actions or [], ensure_ascii=False),
                        notes=payload.notes)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {"id": p.id, "project_id": p.project_id, "page_name": p.page_name,
            "url_path": p.url_path, "description": p.description,
            "common_actions": payload.common_actions or [], "notes": p.notes,
            "element_count": 0, "created_at": _ts(p.created_at), "updated_at": _ts(p.updated_at)}


@router.patch("/ui-pages/{page_id}")
async def update_page(page_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(UIPageKnowledge).where(UIPageKnowledge.id == page_id))).scalars().first()
    if not p:
        raise HTTPException(status_code=404, detail="Page not found")
    for k in ("page_name", "url_path", "description", "notes"):
        if k in payload and payload[k] is not None:
            setattr(p, k, payload[k])
    if isinstance(payload.get("common_actions"), list):
        p.common_actions_json = json.dumps(payload["common_actions"], ensure_ascii=False)
    await db.commit()
    return {"id": p.id, "status": "updated"}


@router.delete("/ui-pages/{page_id}")
async def delete_page(page_id: str, db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(UIPageKnowledge).where(UIPageKnowledge.id == page_id))).scalars().first()
    if not p:
        raise HTTPException(status_code=404, detail="Page not found")
    await db.delete(p)
    await db.commit()
    return {"status": "deleted", "id": page_id}


# ---------- Execution (background + polling, §16-17, §37) ----------
@router.post("/ui-tests/{case_id}/run")
async def run_ui_test(case_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    if not payload.get("environment_id"):
        raise HTTPException(status_code=400, detail="environment_id is required.")
    try:
        return await PR.start_ui_run(
            db, case_id, payload["environment_id"], payload.get("test_run_id"),
            payload.get("flow_vars") or {}, payload.get("changed_by") or "user",
            payload.get("confirm_prod") or False,
            payload.get("browser") or "chromium", payload.get("force") or False)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/executions/{execution_id}/ui-status")
async def ui_status(execution_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await PR.get_ui_status(db, execution_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/executions/{execution_id}/ui-cancel")
async def ui_cancel(execution_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await PR.cancel_ui_run(execution_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ui-suites:run")
async def run_ui_suite(payload: dict, db: AsyncSession = Depends(get_db)):
    """Starts background UI runs for N cases (or smoke set). Returns execution_ids immediately."""
    ids = payload.get("test_case_ids") or []
    environment_id = payload.get("environment_id")
    if not environment_id:
        raise HTTPException(status_code=400, detail="environment_id is required.")
    if payload.get("smoke_only"):
        rows = (await db.execute(select(UIAutomationScript.test_case_id).where(
            UIAutomationScript.is_smoke == True,
            UIAutomationScript.status == "APPROVED"))).scalars().all()
        if payload.get("project_id"):
            cases = (await db.execute(select(TestCase).where(
                TestCase.id.in_(rows),
                TestCase.project_id == payload["project_id"]) if rows else select(TestCase).where(False)
            )).scalars().all()
            ids = [c.id for c in cases]
        else:
            ids = list(rows)
    ids = ids[:30]  # background suite cap
    started, skipped = [], []
    for cid in ids:
        try:
            out = await PR.start_ui_run(
                db, cid, environment_id, payload.get("test_run_id"),
                {}, payload.get("changed_by") or "user",
                payload.get("confirm_prod") or False, "chromium",
                payload.get("force") or False)
            started.append({"test_case_id": cid, **out})
        except ValueError as e:
            skipped.append({"test_case_id": cid, "reason": str(e)})
    return {"started": started, "skipped": skipped,
            "test_run_id": started[0]["test_run_id"] if started else payload.get("test_run_id")}


@router.post("/executions/{execution_id}/analyze-ui-fail")
async def analyze_ui_fail(execution_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    from app.qa.ui_testing import failure_analyzer as _FA
    try:
        return await _FA.analyze_ui_failure(db, execution_id,
                                            payload.get("preferred_provider"), payload.get("model"))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/executions/{execution_id}/ui-bug:draft")
async def draft_ui_bug(execution_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    """Phase 2 bug draft + UI block (browser/screen/failed step/evidence), redacted."""
    from app.qa.execution_models import TestEvidence as _TE
    try:
        draft = await X.draft_bug_report(db, execution_id,
                                         payload.get("preferred_provider"), payload.get("model"))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    ev_rows = (await db.execute(select(_TE).where(_TE.execution_id == execution_id))).scalars().all()
    shots = [e.file_path for e in ev_rows if e.evidence_type == "screenshot"]
    trace = next((e.file_path for e in ev_rows if e.title.startswith("Playwright trace")), None)
    tech = next((e.text_content or "" for e in ev_rows if e.evidence_type == "console_error"), "")
    actual_doc = {}
    try:
        import json as _json
        actual_doc = _json.loads(draft.get("actual_result") or "{}")
    except Exception:
        pass
    fs = actual_doc.get("failed_step", {}) or {}
    ui_vi = (f"Trình duyệt: chromium | URL: {actual_doc.get('current_url', '—')} | "
             f"Step lỗi: {fs.get('label', '—')} | Screenshot: {len(shots)} ảnh"
             + (f" | Trace: có" if trace else ""))
    ui_ja = (f"【環境】chromium\n【対象画面】{actual_doc.get('current_url', '—')}\n"
             f"【実際結果】Step「{fs.get('label', '—')}」で失敗\n"
             f"【エビデンス】スクリーンショット{len(shots)}件"
             + ("、trace有り" if trace else "") + "\n"
             f"【再現率】{draft.get('reproduction_rate', '不明')}")
    draft["ui_browser"] = "chromium"
    draft["ui_current_url"] = actual_doc.get("current_url", "")
    draft["ui_failed_step"] = fs
    draft["ui_screenshots"] = shots
    draft["ui_trace"] = trace
    draft["ui_console_network_excerpt"] = (tech or "")[:2000]
    draft["summary_vi"] = (draft.get("summary_vi") or "") + f"\n{ui_vi}"
    draft["summary_ja"] = (draft.get("summary_ja") or "") + f"\n{ui_ja}"
    draft["notes_ja"] = draft.get("notes_ja") or ""
    return draft


# ---------- Coverage (§54) ----------
@router.get("/coverage/ui")
async def ui_coverage(project_id: str, db: AsyncSession = Depends(get_db)):
    reqs = (await db.execute(select(WorkItem).where(
        WorkItem.project_id == project_id, WorkItem.item_type == "REQUIREMENT"))).scalars().all()
    out = []
    for req in reqs:
        cases = (await db.execute(select(TestCase).where(
            TestCase.requirement_id == req.id))).scalars().all()
        web_auto = manual_pass = api_pass = web_pass = 0
        last_ui = None
        for tc in cases:
            ttype = await test_type_of(db, tc.id)
            last_ex = (await db.execute(select(TestExecution).where(
                TestExecution.test_case_id == tc.id).order_by(
                desc(TestExecution.updated_at)).limit(1))).scalars().first()
            st = last_ex.status if last_ex else None
            if ttype == "WEB_UI":
                web_auto += 1
                if st == "PASS":
                    web_pass += 1
                if last_ex and (not last_ui or last_ex.updated_at > last_ui["at"]):
                    from datetime import datetime as _dt
                    last_ui = {"status": st, "at": last_ex.updated_at}
            elif ttype == "API":
                if st == "PASS":
                    api_pass += 1
            else:
                if st == "PASS":
                    manual_pass += 1
        out.append({"requirement_id": req.id, "req_code": req.req_code, "title": req.title,
                    "design_total": len(cases), "web_automated": web_auto,
                    "manual_pass": manual_pass, "api_pass": api_pass, "web_pass": web_pass,
                    "last_ui_result": last_ui["status"] if last_ui else None})
    return out


@router.get("/ui-candidates")
async def ui_candidates(project_id: str, limit: int = 20, db: AsyncSession = Depends(get_db)):
    from app.qa.ui_testing import failure_analyzer as _FA
    return await _FA.recommend_candidates(db, project_id, min(limit, 50))


@router.get("/overview/ui")
async def ui_overview(project_id: str, db: AsyncSession = Depends(get_db)):
    """Phase 4 dashboard numbers (§55). Frontend merges into QA Overview."""
    scripts = (await db.execute(select(UIAutomationScript).join(
        TestCase, TestCase.id == UIAutomationScript.test_case_id).where(
        TestCase.project_id == project_id))).scalars().all()
    automated = len(scripts)
    needs_update = sum(1 for s in scripts if s.status == "NEEDS_UPDATE")
    review_required = sum(1 for s in scripts if s.status == "REVIEW_REQUIRED")
    flaky = sum(1 for s in scripts if s.flaky_flag)
    smoke = sum(1 for s in scripts if s.is_smoke)
    ui_pass = ui_fail = 0
    recent_failures = []
    if scripts:
        ids = [s.test_case_id for s in scripts]
        ui_pass = (await db.execute(select(func.count(TestExecution.id)).where(
            TestExecution.test_case_id.in_(ids), TestExecution.status == "PASS"))).scalar() or 0
        ui_fail = (await db.execute(select(func.count(TestExecution.id)).where(
            TestExecution.test_case_id.in_(ids), TestExecution.status == "FAIL"))).scalar() or 0
        recent = (await db.execute(select(TestExecution).where(
            TestExecution.test_case_id.in_(ids), TestExecution.status == "FAIL").order_by(
            desc(TestExecution.updated_at)).limit(5))).scalars().all()
        for r in recent:
            tc = (await db.execute(select(TestCase).where(TestCase.id == r.test_case_id))).scalars().first()
            recent_failures.append({"execution_id": r.id, "tc_code": tc.tc_code if tc else "",
                                    "title": tc.title if tc else ""})
    manual_remaining = (await db.execute(select(func.count(TestCase.id)).where(
        TestCase.project_id == project_id, TestCase.status == "APPROVED",
        ~TestCase.id.in_([s.test_case_id for s in scripts] or [""])))).scalar() or 0
    return {"automated": automated, "needs_update": needs_update,
            "review_required": review_required, "flaky": flaky, "smoke": smoke,
            "ui_pass": ui_pass, "ui_fail": ui_fail,
            "recent_failures": recent_failures, "manual_remaining": manual_remaining}
