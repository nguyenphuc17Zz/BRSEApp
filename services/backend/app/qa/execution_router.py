"""QA Workspace Phase 2 REST API: runs, executions, evidence, bugs, retest, reports."""
import json
import re
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy import select, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import DATA_DIR
from app.core.database import get_db
from app.intelligence.models import WorkItem, WorkItemEvidence, ProjectRelationship
from app.qa.models import TestCase, TestStep, RequirementCoverage
from app.qa.execution_models import (
    TestRun, TestExecution, TestEvidence, TestExecutionHistory, QAReport,
)
from app.qa import schemas as S
from app.qa import execution_engines as X
from app.qa import engines as E1

router = APIRouter(prefix="/api/qa", tags=["QA Workspace Phase 2"])

EVIDENCE_DIR = Path(DATA_DIR) / "qa-evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_SUFFIX = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
                         ".log", ".txt", ".json", ".har", ".csv", ".pdf"}


def _ts(v) -> str:
    try:
        return v.isoformat() if v else ""
    except Exception:
        return ""


def _scope(run: TestRun) -> dict:
    try:
        return json.loads(run.scope_json or "{}")
    except Exception:
        return {}


def ser_run(run: TestRun, progress: Optional[dict] = None) -> dict:
    return {"id": run.id, "project_id": run.project_id, "run_code": run.run_code or "",
            "name": run.name, "version_build": run.version_build or "",
            "environment": run.environment or "", "scope": _scope(run),
            "start_date": run.start_date, "end_date": run.end_date,
            "tester": run.tester, "status": run.status,
            "run_type": getattr(run, "run_type", None) or "MANUAL",
            "notes": run.notes,
            "progress": progress or {}, "created_at": _ts(run.created_at),
            "updated_at": _ts(run.updated_at)}


async def ser_execution(db: AsyncSession, ex: TestExecution) -> dict:
    tc = (await db.execute(select(TestCase).where(TestCase.id == ex.test_case_id))).scalars().first()
    req = await E1.get_requirement(db, ex.requirement_id)
    ev_count = (await db.execute(select(func.count(TestEvidence.id)).where(
        TestEvidence.execution_id == ex.id))).scalar() or 0
    bug_code = None
    if ex.bug_work_item_id:
        bug = (await db.execute(
            select(WorkItem).where(WorkItem.id == ex.bug_work_item_id))).scalars().first()
        bug_code = bug.req_code if bug else None
    return {"id": ex.id, "test_run_id": ex.test_run_id, "test_case_id": ex.test_case_id,
            "tc_code": tc.tc_code if tc else "", "tc_title": tc.title if tc else "",
            "requirement_id": ex.requirement_id, "req_code": getattr(req, "req_code", None),
            "acceptance_criterion_id": ex.acceptance_criterion_id,
            "attempt_no": ex.attempt_no, "prev_execution_id": ex.prev_execution_id,
            "status": ex.status, "actual_result": ex.actual_result, "notes": ex.notes,
            "fail_reason": ex.fail_reason, "tester": ex.tester,
            "executed_at": _ts(ex.executed_at), "bug_work_item_id": ex.bug_work_item_id,
            "bug_code": bug_code, "evidence_count": ev_count,
            "created_at": _ts(ex.created_at), "updated_at": _ts(ex.updated_at)}


def ser_evidence(e: TestEvidence) -> dict:
    return {"id": e.id, "execution_id": e.execution_id, "test_case_id": e.test_case_id,
            "requirement_id": e.requirement_id, "bug_work_item_id": e.bug_work_item_id,
            "evidence_type": e.evidence_type, "title": e.title or "",
            "text_content": e.text_content, "file_path": e.file_path,
            "mime_type": e.mime_type, "created_by": e.created_by,
            "created_at": _ts(e.created_at)}


def ser_report(r: QAReport) -> dict:
    try:
        metrics = json.loads(r.metrics_json or "{}")
    except Exception:
        metrics = {}
    return {"id": r.id, "project_id": r.project_id, "test_run_id": r.test_run_id,
            "report_type": r.report_type, "scope_build": r.scope_build or "",
            "markdown_vi": r.markdown_vi or "", "markdown_ja": r.markdown_ja or "",
            "metrics": metrics, "status": r.status, "ai_generated": r.ai_generated,
            "created_at": _ts(r.created_at)}


async def _get_run(db: AsyncSession, run_id: str) -> TestRun:
    run = (await db.execute(select(TestRun).where(TestRun.id == run_id))).scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Test run not found")
    return run


# ---------- Test Runs ----------
@router.post("/test-runs", response_model=S.TestRunResponse)
async def create_test_run(project_id: str, payload: S.TestRunCreate, db: AsyncSession = Depends(get_db)):
    run = await X.create_run(db, project_id, payload.model_dump())
    await db.commit()
    await db.refresh(run)
    return ser_run(run, await X.run_progress(db, run.id))


@router.get("/test-runs", response_model=List[S.TestRunResponse])
async def list_test_runs(project_id: Optional[str] = None, status: Optional[str] = None,
                         search: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(TestRun).order_by(desc(TestRun.created_at))
    if project_id:
        stmt = stmt.where(TestRun.project_id == project_id)
    if status:
        stmt = stmt.where(TestRun.status == status.upper())
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(TestRun.name.like(like), TestRun.version_build.like(like),
                             TestRun.run_code.like(like)))
    runs = (await db.execute(stmt.limit(200))).scalars().all()
    return [ser_run(r, await X.run_progress(db, r.id)) for r in runs]


@router.get("/test-runs/{run_id}")
async def get_test_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await _get_run(db, run_id)
    prog = await X.run_progress(db, run_id)
    ex_rows = (await db.execute(select(TestExecution).where(
        TestExecution.test_run_id == run_id).order_by(TestExecution.created_at))).scalars().all()
    executions = [await ser_execution(db, e) for e in ex_rows]
    bug_ids = sorted({e.bug_work_item_id for e in ex_rows if e.bug_work_item_id})
    bugs = []
    if bug_ids:
        for b in (await db.execute(select(WorkItem).where(WorkItem.id.in_(bug_ids)))).scalars().all():
            bugs.append({"id": b.id, "bug_code": b.req_code, "title": b.title,
                         "status": b.status, "ux_status": X.bug_ux_status(b.status, b.details_json),
                         "priority": b.priority})
    ev_rows = (await db.execute(select(TestEvidence).where(
        TestEvidence.execution_id.in_([e.id for e in ex_rows])) if ex_rows else select(TestEvidence).where(False)
    )).scalars().all()
    failures = [e for e in executions if e["status"] in ("FAIL", "BLOCKED")]
    risks = [f"{f['tc_code']} {f['tc_title']} ({f['status']})" for f in failures]
    return {"run": ser_run(run, prog), "progress": prog, "executions": executions,
            "failures": failures, "bugs": bugs,
            "evidence": [ser_evidence(e) for e in ev_rows], "risks": risks}


@router.patch("/test-runs/{run_id}", response_model=S.TestRunResponse)
async def update_test_run(run_id: str, payload: S.TestRunUpdate, db: AsyncSession = Depends(get_db)):
    run = await _get_run(db, run_id)
    data = payload.model_dump(exclude_none=True)
    status = data.pop("status", None)
    for k, v in data.items():
        if hasattr(run, k):
            setattr(run, k, v)
    await db.flush()
    warnings: List[str] = []
    if status:
        run, warnings = await X.set_run_status(db, run, status)
    else:
        await db.commit()
        await db.refresh(run)
    out = ser_run(run, await X.run_progress(db, run.id))
    out["warnings"] = warnings
    return out


@router.post("/test-runs/{run_id}/cases")
async def add_cases(run_id: str, payload: S.AddCasesRequest, db: AsyncSession = Depends(get_db)):
    run = await _get_run(db, run_id)
    if run.status == "COMPLETED":
        raise HTTPException(status_code=400, detail="Cannot add cases to a COMPLETED run.")
    scope = payload.scope or {}
    cases, warnings = await X.select_cases_for_run(db, run.project_id, scope)
    added = await X.add_cases_to_run(db, run, cases)
    await db.commit()
    return {"added": added, "matched": len(cases), "warnings": warnings,
            "progress": await X.run_progress(db, run.id)}


@router.get("/test-runs/{run_id}/next")
async def next_execution(run_id: str, after: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    await _get_run(db, run_id)
    nxt = await X.next_pending_execution(db, run_id, after)
    if not nxt:
        return {"execution": None, "progress": await X.run_progress(db, run_id)}
    return {"execution": await ser_execution(db, nxt),
            "progress": await X.run_progress(db, run_id)}


# ---------- Executions ----------
@router.get("/executions/{execution_id}")
async def get_execution_detail(execution_id: str, db: AsyncSession = Depends(get_db)):
    ex = await X.get_execution(db, execution_id)
    if not ex:
        raise HTTPException(status_code=404, detail="Execution not found")
    tc = (await db.execute(select(TestCase).options(selectinload(TestCase.steps)).where(
        TestCase.id == ex.test_case_id))).scalars().first()
    req = await E1.get_requirement(db, ex.requirement_id)
    ac = None
    if ex.acceptance_criterion_id:
        from app.qa.models import AcceptanceCriterion
        ac = (await db.execute(select(AcceptanceCriterion).where(
            AcceptanceCriterion.id == ex.acceptance_criterion_id))).scalars().first()
    ev_rows = (await db.execute(select(TestEvidence).where(
        TestEvidence.execution_id == ex.id).order_by(TestEvidence.created_at))).scalars().all()
    hist = (await db.execute(select(TestExecutionHistory).where(
        TestExecutionHistory.execution_id == ex.id).order_by(TestExecutionHistory.created_at))).scalars().all()
    attempts = (await db.execute(select(TestExecution).where(
        TestExecution.test_run_id == ex.test_run_id,
        TestExecution.test_case_id == ex.test_case_id).order_by(TestExecution.attempt_no))).scalars().all()
    bug = None
    if ex.bug_work_item_id:
        b = (await db.execute(select(WorkItem).where(
            WorkItem.id == ex.bug_work_item_id))).scalars().first()
        if b:
            bug = {"id": b.id, "bug_code": b.req_code, "title": b.title,
                   "status": b.status, "ux_status": X.bug_ux_status(b.status, b.details_json)}
    return {
        "execution": await ser_execution(db, ex),
        "test_case": {"id": tc.id, "tc_code": tc.tc_code, "title": tc.title,
                      "purpose": tc.purpose, "case_type": tc.case_type,
                      "preconditions": tc.preconditions, "expected_result": tc.expected_result,
                      "steps": [{"step_order": s.step_order, "action": s.action,
                                 "expected": s.expected} for s in sorted(tc.steps or [], key=lambda x: x.step_order)]} if tc else None,
        "requirement": {"id": req.id, "req_code": getattr(req, "req_code", None),
                        "title": req.title, "description": req.description} if req else None,
        "acceptance_criterion": {"id": ac.id, "ac_code": ac.ac_code, "given_text": ac.given_text,
                                 "when_text": ac.when_text, "then_text": ac.then_text} if ac else None,
        "evidence": [ser_evidence(e) for e in ev_rows],
        "bug": bug,
        "attempts": [{"id": a.id, "attempt_no": a.attempt_no, "status": a.status,
                      "actual_result": a.actual_result} for a in attempts],
        "history": [{"changed_by": h.changed_by, "field": h.field,
                     "old_value": h.old_value, "new_value": h.new_value,
                     "at": _ts(h.created_at)} for h in hist],
    }


@router.post("/executions/{execution_id}/start")
async def start_execution(execution_id: str, tester: Optional[str] = None,
                          db: AsyncSession = Depends(get_db)):
    try:
        ex = await X.set_execution_result(db, execution_id, "RUNNING", tester=tester)
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e).lower() else 400, detail=str(e))
    return await ser_execution(db, ex)


@router.post("/executions/{execution_id}/result")
async def save_result(execution_id: str, payload: S.ExecutionResultRequest,
                      db: AsyncSession = Depends(get_db)):
    try:
        ex = await X.set_execution_result(
            db, execution_id, payload.status, payload.actual_result,
            payload.notes, payload.fail_reason, payload.tester,
            payload.changed_by or "user")
    except ValueError as e:
        msg = str(e)
        raise HTTPException(status_code=404 if "not found" in msg.lower() else 400, detail=msg)
    return await ser_execution(db, ex)


@router.post("/executions/{execution_id}/rewrite-actual")
async def rewrite_actual(execution_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    """AI draft: rewrite user's actual result more clearly. Returns text only, never saves."""
    from app.qa.llm import generate_qa_json
    raw = (payload.get("actual_result") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="actual_result is required.")
    parsed = await generate_qa_json(
        f"Rewrite this QA actual-result note clearly and factually in Vietnamese. "
        f"Do NOT change its meaning, do NOT add new facts:\n\"{raw[:1500]}\"\n"
        f"Return strict JSON: {{\"rewritten\": \"...\"}}",
        "You are a QA assistant that clarifies wording without changing meaning.",
        payload.get("preferred_provider"), payload.get("model"), max_tokens=600)
    return {"rewritten": parsed.get("rewritten", raw) if parsed else raw}


# ---------- Evidence ----------
@router.post("/executions/{execution_id}/evidence", response_model=S.EvidenceResponse)
async def add_text_evidence(execution_id: str, payload: S.EvidenceCreate,
                            db: AsyncSession = Depends(get_db)):
    try:
        ev = await X.add_evidence(db, execution_id, payload.model_dump(), payload.changed_by or "user")
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e).lower() else 400, detail=str(e))
    return ser_evidence(ev)


@router.post("/executions/{execution_id}/evidence/upload", response_model=S.EvidenceResponse)
async def upload_evidence(execution_id: str, file: UploadFile = File(...),
                          title: Optional[str] = Form(None),
                          evidence_type: str = Form("screenshot"),
                          changed_by: str = Form("user"),
                          db: AsyncSession = Depends(get_db)):
    ex = await X.get_execution(db, execution_id)
    if not ex:
        raise HTTPException(status_code=404, detail="Execution not found")
    etype = (evidence_type or "screenshot").lower()
    if etype not in X.VALID_EVIDENCE_TYPES:
        raise HTTPException(status_code=400, detail="Invalid evidence type.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIX:
        raise HTTPException(status_code=400, detail=f"File type not allowed: {suffix or '(none)'}")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 10MB limit.")
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", Path(file.filename or "evidence").name)[:120]
    run_dir = EVIDENCE_DIR / ex.test_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    dest = run_dir / f"{ex.id[:8]}_{safe_name}"
    dest.write_bytes(content)
    rel = dest.relative_to(Path(DATA_DIR)).as_posix()
    ev = await X.add_evidence(db, execution_id, {
        "evidence_type": etype, "title": title or file.filename or "attachment",
        "file_path": rel, "mime_type": file.content_type,
    }, changed_by)
    return ser_evidence(ev)


@router.get("/executions/{execution_id}/evidence", response_model=List[S.EvidenceResponse])
async def list_evidence(execution_id: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(TestEvidence).where(
        TestEvidence.execution_id == execution_id).order_by(TestEvidence.created_at))).scalars().all()
    return [ser_evidence(e) for e in rows]


@router.get("/evidence/{evidence_id}/file")
async def serve_evidence_file(evidence_id: str, db: AsyncSession = Depends(get_db)):
    e = (await db.execute(select(TestEvidence).where(TestEvidence.id == evidence_id))).scalars().first()
    if not e or not e.file_path:
        raise HTTPException(status_code=404, detail="Evidence file not found")
    base = Path(DATA_DIR).resolve()
    target = (base / e.file_path).resolve()
    if base not in target.parents and target != base:
        raise HTTPException(status_code=400, detail="Invalid file path.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File missing on disk.")
    return FileResponse(str(target), media_type=e.mime_type or "application/octet-stream",
                        filename=target.name)


# ---------- Bugs ----------
@router.post("/executions/{execution_id}/bug:draft", response_model=S.BugDraftResponse)
async def draft_bug(execution_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    try:
        return await X.draft_bug_report(db, execution_id,
                                        payload.get("preferred_provider"), payload.get("model"))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/executions/{execution_id}/bug")
async def create_bug(execution_id: str, payload: S.BugCreateRequest, db: AsyncSession = Depends(get_db)):
    try:
        bug = await X.create_bug_from_execution(db, execution_id, payload.model_dump(),
                                                payload.status, payload.changed_by or "user")
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e).lower() else 400, detail=str(e))
    return await bug_detail(bug.id, db)


def _bug_trace(db_rows, bug: WorkItem) -> dict:
    try:
        details = json.loads(bug.details_json or "{}")
    except Exception:
        details = {}
    return details


async def bug_detail(bug_id: str, db: AsyncSession) -> dict:
    bug = (await db.execute(select(WorkItem).where(
        WorkItem.id == bug_id, WorkItem.item_type == "BUG"))).scalars().first()
    if not bug:
        raise HTTPException(status_code=404, detail="Bug not found")
    details = _bug_trace(None, bug)
    rels = (await db.execute(select(ProjectRelationship).where(
        ProjectRelationship.source_type == "bug",
        ProjectRelationship.source_id == bug_id))).scalars().all()
    trace = {"requirement_id": None, "test_case_id": None,
             "test_run_id": None, "execution_id": details.get("execution_id")}
    for r in rels:
        if r.target_type == "requirement":
            trace["requirement_id"] = r.target_id
        elif r.target_type == "test_case":
            trace["test_case_id"] = r.target_id
        elif r.target_type == "test_run":
            trace["test_run_id"] = r.target_id
        elif r.target_type == "test_execution":
            trace["execution_id"] = r.target_id
    ev_rows = (await db.execute(select(WorkItemEvidence).where(
        WorkItemEvidence.work_item_id == bug_id))).scalars().all()
    req = tc = run = None
    if trace["requirement_id"]:
        req = await E1.get_requirement(db, trace["requirement_id"])
    if trace["test_case_id"]:
        tc = (await db.execute(select(TestCase).where(
            TestCase.id == trace["test_case_id"]))).scalars().first()
    if trace["test_run_id"]:
        run = (await db.execute(select(TestRun).where(
            TestRun.id == trace["test_run_id"]))).scalars().first()
    # retest attempts
    retests = []
    if trace["execution_id"] and trace["test_case_id"] and trace["test_run_id"]:
        att = (await db.execute(select(TestExecution).where(
            TestExecution.test_run_id == trace["test_run_id"],
            TestExecution.test_case_id == trace["test_case_id"]).order_by(TestExecution.attempt_no)
        )).scalars().all()
        retests = [{"id": a.id, "attempt_no": a.attempt_no, "status": a.status} for a in att]
    return {
        "id": bug.id, "project_id": bug.project_id, "bug_code": bug.req_code,
        "title": bug.title, "description": bug.description or "", "details": details,
        "status": bug.status, "ux_status": X.bug_ux_status(bug.status, bug.details_json),
        "priority": bug.priority, "assignee": bug.assignee,
        "requirement_id": trace["requirement_id"],
        "req_code": getattr(req, "req_code", None),
        "requirement_title": req.title if req else None,
        "test_case_id": trace["test_case_id"],
        "tc_code": tc.tc_code if tc else None,
        "test_case_title": tc.title if tc else None,
        "test_run_id": trace["test_run_id"],
        "run_code": run.run_code if run else None,
        "execution_id": trace["execution_id"],
        "evidence": [{"id": e.id, "source_type": e.source_type, "quote_text": e.quote_text,
                      "author": e.author} for e in ev_rows],
        "retests": retests,
        "created_at": _ts(bug.created_at), "updated_at": _ts(bug.updated_at),
    }


@router.get("/bugs")
async def list_bugs(project_id: Optional[str] = None, status: Optional[str] = None,
                    priority: Optional[str] = None, requirement_id: Optional[str] = None,
                    test_run_id: Optional[str] = None, assignee: Optional[str] = None,
                    search: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(WorkItem).where(WorkItem.item_type == "BUG").order_by(desc(WorkItem.created_at))
    if project_id:
        stmt = stmt.where(WorkItem.project_id == project_id)
    if priority:
        stmt = stmt.where(WorkItem.priority == priority.upper())
    if assignee:
        stmt = stmt.where(WorkItem.assignee == assignee)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(WorkItem.title.like(like), WorkItem.req_code.like(like)))
    bugs = (await db.execute(stmt.limit(200))).scalars().all()
    if requirement_id or test_run_id:
        rels = (await db.execute(select(ProjectRelationship).where(
            ProjectRelationship.source_type == "bug"))).scalars().all()
        keep = set()
        for r in rels:
            if requirement_id and r.target_type == "requirement" and r.target_id == requirement_id:
                keep.add(r.source_id)
            if test_run_id and r.target_type == "test_run" and r.target_id == test_run_id:
                keep.add(r.source_id)
        bugs = [b for b in bugs if b.id in keep]
    out = []
    for b in bugs:
        ux = X.bug_ux_status(b.status, b.details_json)
        if status and ux != status.upper() and b.status != status.upper():
            continue
        out.append({"id": b.id, "project_id": b.project_id, "bug_code": b.req_code,
                    "title": b.title, "status": b.status, "ux_status": ux,
                    "priority": b.priority, "assignee": b.assignee,
                    "created_at": _ts(b.created_at), "updated_at": _ts(b.updated_at)})
    return out


@router.get("/bugs/{bug_id}")
async def get_bug(bug_id: str, db: AsyncSession = Depends(get_db)):
    return await bug_detail(bug_id, db)


@router.patch("/bugs/{bug_id}")
async def update_bug(bug_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    bug = (await db.execute(select(WorkItem).where(
        WorkItem.id == bug_id, WorkItem.item_type == "BUG"))).scalars().first()
    if not bug:
        raise HTTPException(status_code=404, detail="Bug not found")
    changed_by = payload.get("changed_by") or "user"
    if payload.get("ux_status"):
        ux = payload["ux_status"].upper()
        if ux not in X.BUG_UX_TO_STATUS:
            raise HTTPException(status_code=400, detail="Invalid ux_status.")
        old = bug.status
        bug.status = X.BUG_UX_TO_STATUS[ux]
        try:
            d = json.loads(bug.details_json or "{}")
        except Exception:
            d = {}
        d.pop("qa_retest", None)
        if ux == "CLOSED":
            d["qa_closed"] = True
        bug.details_json = json.dumps(d, ensure_ascii=False)
        # audit onto linked execution if any
        try:
            details = json.loads(bug.details_json or "{}")
        except Exception:
            details = {}
        if details.get("execution_id"):
            await X.log_history(db, details.get("execution_id"), "bug",
                                f"{bug_id}:{old}", f"{bug_id}:{bug.status}", changed_by)
    elif payload.get("status"):
        st = payload["status"].upper()
        if st not in ("PROPOSED", "CONFIRMED", "IN_PROGRESS", "BLOCKED", "DONE", "REJECTED", "SUPERSEDED", "NEEDS_CONFIRMATION", "CONFLICT"):
            raise HTTPException(status_code=400, detail="Invalid status.")
        bug.status = st
    if payload.get("assignee") is not None:
        bug.assignee = payload["assignee"]
    if payload.get("priority"):
        bug.priority = payload["priority"].upper()
    if payload.get("title"):
        bug.title = payload["title"][:255]
    await db.commit()
    return await bug_detail(bug.id, db)


@router.post("/executions/{execution_id}/retest")
async def retest_execution(execution_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    try:
        new_ex = await X.create_retest(db, execution_id, (payload or {}).get("changed_by") or "user")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await ser_execution(db, new_ex)


# ---------- Reports ----------
@router.post("/test-runs/{run_id}/reports", response_model=S.ReportResponse)
async def generate_report(run_id: str, payload: S.ReportGenerateRequest,
                          db: AsyncSession = Depends(get_db)):
    if payload.report_type not in ("summary", "completion", "daily"):
        raise HTTPException(status_code=400, detail="Invalid report_type.")
    try:
        r = await X.draft_report(db, run_id, payload.report_type,
                                 payload.preferred_provider, payload.model,
                                 payload.created_by or "user")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ser_report(r)


@router.get("/test-runs/{run_id}/reports", response_model=List[S.ReportResponse])
async def list_reports(run_id: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(QAReport).where(
        QAReport.test_run_id == run_id).order_by(desc(QAReport.created_at)))).scalars().all()
    return [ser_report(r) for r in rows]


@router.get("/reports/{report_id}", response_model=S.ReportResponse)
async def get_report(report_id: str, db: AsyncSession = Depends(get_db)):
    r = (await db.execute(select(QAReport).where(QAReport.id == report_id))).scalars().first()
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    return ser_report(r)


@router.patch("/reports/{report_id}", response_model=S.ReportResponse)
async def approve_report(report_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    r = (await db.execute(select(QAReport).where(QAReport.id == report_id))).scalars().first()
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    if payload.get("status"):
        if payload["status"].upper() not in ("DRAFT", "APPROVED"):
            raise HTTPException(status_code=400, detail="Invalid status.")
        r.status = payload["status"].upper()
    await db.commit()
    await db.refresh(r)
    return ser_report(r)


# ---------- Execution coverage (§18) ----------
@router.get("/execution-coverage")
async def execution_coverage(project_id: str, db: AsyncSession = Depends(get_db)):
    reqs = (await db.execute(select(WorkItem).where(
        WorkItem.project_id == project_id, WorkItem.item_type == "REQUIREMENT"))).scalars().all()
    out = []
    for req in reqs:
        cov = await X.refresh_exec_coverage(db, req.id)
        design_pct = round(cov.tc_total and (cov.tc_total / cov.tc_total) * 100 or 0)
        exec_pct = round((cov.exec_executed / cov.exec_total * 100) if cov.exec_total else 0)
        out.append({"requirement_id": req.id, "req_code": req.req_code, "title": req.title,
                    "design_total": cov.tc_total, "design_coverage_pct": 100 if cov.tc_total else 0,
                    "exec_total": cov.exec_total, "exec_executed": cov.exec_executed,
                    "exec_passed": cov.exec_passed, "exec_failed": cov.exec_failed,
                    "exec_blocked": cov.exec_blocked,
                    "execution_coverage_pct": exec_pct, "design_pct": design_pct,
                    "exec_status": cov.exec_status, "last_result": cov.last_result,
                    "last_build": cov.last_build})
    await db.commit()
    return out
