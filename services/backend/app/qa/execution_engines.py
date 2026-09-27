"""QA Phase 2 engines: runs, executions, evidence, bugs, retest, reports, execution coverage."""
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.intelligence.models import WorkItem, WorkItemEvidence, ProjectRelationship
from app.qa.models import TestCase, RequirementCoverage
from app.qa.execution_models import (
    TestRun, TestExecution, TestEvidence, TestExecutionHistory, QAReport,
)
from app.qa.llm import generate_qa_json
from app.qa import engines as E1

VALID_RUN_STATUS = {"DRAFT", "READY", "IN_PROGRESS", "COMPLETED", "CANCELLED"}
VALID_EXEC_STATUS = {"NOT_RUN", "RUNNING", "PASS", "FAIL", "BLOCKED", "SKIPPED", "ERROR"}
VALID_EVIDENCE_TYPES = {
    "screenshot", "note", "log", "api_request", "api_response",
    "console_error", "db_result", "file", "url",
}

# UX label map over reused WorkItem statuses (no workflow change on WorkItem itself)
BUG_UX_TO_STATUS = {
    "OPEN": "PROPOSED", "CONFIRMED": "CONFIRMED", "IN_PROGRESS": "IN_PROGRESS",
    "FIXED": "DONE", "RETEST": "IN_PROGRESS", "CLOSED": "DONE", "REJECTED": "REJECTED",
}
BUG_STATUS_TO_UX = {
    "PROPOSED": "OPEN", "NEEDS_CONFIRMATION": "OPEN", "CONFIRMED": "CONFIRMED",
    "IN_PROGRESS": "IN_PROGRESS", "BLOCKED": "IN_PROGRESS",
    "DONE": "FIXED", "SUPERSEDED": "CLOSED", "REJECTED": "REJECTED", "CONFLICT": "OPEN",
}


def bug_ux_status(work_status: str, details_json: str = "") -> str:
    try:
        d = json.loads(details_json or "{}")
    except Exception:
        d = {}
    if work_status == "DONE" and d.get("qa_closed"):
        return "CLOSED"
    if work_status == "IN_PROGRESS" and d.get("qa_retest"):
        return "RETEST"
    return BUG_STATUS_TO_UX.get(work_status, work_status)


async def ensure_bug_code(db: AsyncSession, item: WorkItem) -> str:
    code = (item.req_code or "").strip()
    if code.startswith("BUG-"):
        return code
    res = await db.execute(
        select(WorkItem.req_code).where(
            WorkItem.project_id == item.project_id,
            WorkItem.item_type == "BUG",
            WorkItem.req_code.isnot(None),
        )
    )
    max_n = 0
    for (c,) in res.all():
        m = re.search(r"(\d+)$", c or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    item.req_code = f"BUG-{max_n + 1:03d}"
    await db.flush()
    return item.req_code


async def next_run_code(db: AsyncSession, project_id: str) -> str:
    res = await db.execute(select(TestRun.run_code).where(TestRun.project_id == project_id))
    max_n = 0
    for (c,) in res.all():
        m = re.search(r"(\d+)$", c or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"RUN-{max_n + 1:02d}"


async def log_history(db: AsyncSession, execution_id: Optional[str], field: str,
                      old: Optional[str], new: Optional[str], changed_by: str = "user") -> None:
    if not execution_id:
        return
    db.add(TestExecutionHistory(execution_id=execution_id, changed_by=changed_by,
                                field=field, old_value=old, new_value=new))
    await db.flush()


# ---------- runs ----------
async def create_run(db: AsyncSession, project_id: str, payload: Dict[str, Any]) -> TestRun:
    run = TestRun(
        project_id=project_id,
        run_code=await next_run_code(db, project_id),
        name=(payload.get("name") or "Untitled Test Run").strip()[:255],
        version_build=(payload.get("version_build") or "").strip()[:100],
        environment=(payload.get("environment") or "").strip()[:100],
        scope_json=json.dumps(payload.get("scope") or {}, ensure_ascii=False),
        start_date=payload.get("start_date"),
        end_date=payload.get("end_date"),
        tester=(payload.get("tester") or None),
        status="DRAFT",
        run_type=(payload.get("run_type") or "MANUAL").upper()
        if (payload.get("run_type") or "MANUAL").upper() in (
            "MANUAL", "API", "WEB_UI", "DATA", "REGRESSION", "MIXED") else "MANUAL",
        notes=payload.get("notes"),
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return run


async def select_cases_for_run(
    db: AsyncSession, project_id: str, scope: Dict[str, Any],
) -> Tuple[List[TestCase], List[str]]:
    """Selects cases per scope. Returns (cases, warnings). REJECTED never included."""
    stmt = select(TestCase).where(TestCase.project_id == project_id,
                                  TestCase.status != "REJECTED")
    if scope.get("requirement_ids"):
        stmt = stmt.where(TestCase.requirement_id.in_(scope["requirement_ids"]))
    if scope.get("priorities"):
        stmt = stmt.where(TestCase.priority.in_([p.upper() for p in scope["priorities"]]))
    if scope.get("case_types"):
        stmt = stmt.where(TestCase.case_type.in_(scope["case_types"]))
    if scope.get("approved_only", True):
        stmt = stmt.where(TestCase.status.in_(["REVIEWED", "APPROVED"]))
    if scope.get("test_case_ids"):
        stmt = stmt.where(TestCase.id.in_(scope["test_case_ids"]))
    cases = (await db.execute(stmt.order_by(TestCase.tc_code))).scalars().all()
    warnings: List[str] = []
    skipped_draft = (await db.execute(
        select(func.count(TestCase.id)).where(
            TestCase.project_id == project_id, TestCase.status == "DRAFT",
            *([TestCase.requirement_id.in_(scope["requirement_ids"])] if scope.get("requirement_ids") else []),
        )
    )).scalar() or 0
    if skipped_draft and scope.get("approved_only", True):
        warnings.append(f"{skipped_draft} DRAFT case(s) excluded — only REVIEWED/APPROVED are added.")
    return list(cases), warnings


async def add_cases_to_run(db: AsyncSession, run: TestRun, cases: List[TestCase]) -> int:
    existing = (await db.execute(
        select(TestExecution.test_case_id).where(TestExecution.test_run_id == run.id)
    )).scalars().all()
    existing_set = set(existing)
    added = 0
    for tc in cases:
        if tc.id in existing_set:
            continue
        snap = {"tc_code": tc.tc_code, "title": tc.title, "expected_result": tc.expected_result}
        db.add(TestExecution(
            test_run_id=run.id, test_case_id=tc.id, requirement_id=tc.requirement_id,
            acceptance_criterion_id=tc.acceptance_criterion_id, attempt_no=1,
            status="NOT_RUN", case_snapshot_json=json.dumps(snap, ensure_ascii=False),
        ))
        added += 1
    await db.flush()
    return added


def _count(statuses: List[str]) -> Dict[str, int]:
    return {
        "total": len(statuses),
        "not_run": sum(1 for s in statuses if s in ("NOT_RUN", "RUNNING")),
        "pass": sum(1 for s in statuses if s == "PASS"),
        "fail": sum(1 for s in statuses if s == "FAIL"),
        "blocked": sum(1 for s in statuses if s == "BLOCKED"),
        "skipped": sum(1 for s in statuses if s == "SKIPPED"),
    }


async def run_progress(db: AsyncSession, run_id: str) -> Dict[str, Any]:
    rows = (await db.execute(
        select(TestExecution.status).where(TestExecution.test_run_id == run_id)
    )).all()
    prog = _count([r[0] for r in rows])
    prog["executed"] = prog["pass"] + prog["fail"] + prog["blocked"] + prog["skipped"]
    return prog


async def set_run_status(db: AsyncSession, run: TestRun, status: str,
                         changed_by: str = "user") -> Tuple[TestRun, List[str]]:
    status = status.upper()
    if status not in VALID_RUN_STATUS:
        raise ValueError(f"Invalid run status: {status}")
    warnings: List[str] = []
    if status == "COMPLETED":
        prog = await run_progress(db, run.id)
        if prog["not_run"] > 0:
            warnings.append(f"{prog['not_run']} execution(s) still NOT_RUN — confirm completion anyway.")
    old = run.status
    run.status = status
    await db.flush()
    await log_history(db, None, "run", f"{run.id}:{old}", f"{run.id}:{status}", changed_by)
    await db.commit()
    await db.refresh(run)
    return run, warnings


# ---------- executions ----------
async def get_execution(db: AsyncSession, execution_id: str) -> Optional[TestExecution]:
    return (await db.execute(
        select(TestExecution).where(TestExecution.id == execution_id))).scalars().first()


async def set_execution_result(
    db: AsyncSession, execution_id: str, status: str,
    actual_result: Optional[str] = None, notes: Optional[str] = None,
    fail_reason: Optional[str] = None, tester: Optional[str] = None,
    changed_by: str = "user",
) -> TestExecution:
    status = status.upper()
    if status not in VALID_EXEC_STATUS:
        raise ValueError(f"Invalid execution status: {status}")
    ex = await get_execution(db, execution_id)
    if not ex:
        raise ValueError("Execution not found")
    if status in ("FAIL", "BLOCKED") and not (actual_result or "").strip():
        raise ValueError("Actual result is required for FAIL/BLOCKED.")
    old = ex.status
    ex.status = status
    if actual_result is not None:
        ex.actual_result = actual_result
    if notes is not None:
        ex.notes = notes
    if fail_reason is not None:
        ex.fail_reason = fail_reason
    if tester:
        ex.tester = tester
    import datetime as _dt
    ex.executed_at = _dt.datetime.utcnow()
    await db.flush()
    await log_history(db, ex.id, "status", old, status, changed_by)
    run = (await db.execute(select(TestRun).where(TestRun.id == ex.test_run_id))).scalars().first()
    if run and run.status in ("READY", "DRAFT") and status in ("RUNNING", "PASS", "FAIL", "BLOCKED", "SKIPPED"):
        await log_history(db, ex.id, "run", f"{run.id}:{run.status}", f"{run.id}:IN_PROGRESS", changed_by)
        run.status = "IN_PROGRESS"
        await db.flush()
    await refresh_exec_coverage(db, ex.requirement_id)
    if run:
        await db.refresh(run)
    await db.commit()
    await db.refresh(ex)
    return ex


async def next_pending_execution(db: AsyncSession, run_id: str,
                                 after_execution_id: Optional[str] = None) -> Optional[TestExecution]:
    stmt = select(TestExecution).where(
        TestExecution.test_run_id == run_id,
        TestExecution.status.in_(["NOT_RUN", "RUNNING"]),
    ).order_by(TestExecution.created_at)
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return None
    if after_execution_id:
        for i, r in enumerate(rows):
            if r.id == after_execution_id and i + 1 < len(rows):
                return rows[i + 1]
    return rows[0]


# ---------- evidence ----------
async def add_evidence(db: AsyncSession, execution_id: str, payload: Dict[str, Any],
                       changed_by: str = "user") -> TestEvidence:
    ex = await get_execution(db, execution_id)
    if not ex:
        raise ValueError("Execution not found")
    etype = (payload.get("evidence_type") or "note").lower()
    if etype not in VALID_EVIDENCE_TYPES:
        raise ValueError(f"Invalid evidence type: {etype}")
    ev = TestEvidence(
        execution_id=ex.id, test_case_id=ex.test_case_id, requirement_id=ex.requirement_id,
        bug_work_item_id=ex.bug_work_item_id,
        evidence_type=etype, title=(payload.get("title") or "").strip()[:255],
        text_content=payload.get("text_content"),
        file_path=payload.get("file_path"), mime_type=payload.get("mime_type"),
        created_by=changed_by,
    )
    db.add(ev)
    await db.flush()
    await log_history(db, ex.id, "evidence", None, f"{ev.id}:{etype}:{ev.title}", changed_by)
    await db.commit()
    await db.refresh(ev)
    return ev


# ---------- bugs ----------
BUG_SYSTEM = (
    "You are a senior QA engineer writing a neutral bug report for a Japanese software project. "
    "Describe facts only from the provided evidence. NEVER blame developers, NEVER guess the root cause, "
    "NEVER claim a cause without evidence. Japanese must use polite neutral keigo."
)


async def draft_bug_report(
    db: AsyncSession, execution_id: str,
    preferred_provider: Optional[str] = None, model: Optional[str] = None,
) -> Dict[str, Any]:
    ex = await get_execution(db, execution_id)
    if not ex:
        raise ValueError("Execution not found")
    tc = (await db.execute(select(TestCase).where(TestCase.id == ex.test_case_id))).scalars().first()
    req = await E1.get_requirement(db, ex.requirement_id)
    run = (await db.execute(select(TestRun).where(TestRun.id == ex.test_run_id))).scalars().first()
    ev_rows = (await db.execute(
        select(TestEvidence).where(TestEvidence.execution_id == ex.id))).scalars().all()
    ev_text = "\n".join(f"- [{e.evidence_type}] {e.title}: {(e.text_content or e.file_path or '')[:300]}"
                        for e in ev_rows) or "(no evidence attached yet — attach evidence before sending)"

    prompt = f"""Draft a bug report from this failed test execution. Facts only.

Requirement [{getattr(req, 'req_code', '') if req else ''}]: {req.title if req else ''}
Test case [{tc.tc_code if tc else ''}]: {tc.title if tc else ''}
Expected: {tc.expected_result if tc else ''}
Actual: {ex.actual_result or ''}
Fail reason: {ex.fail_reason or ''}
Build: {run.version_build if run else ''} | Environment: {run.environment if run else ''}
Evidence:
{ev_text}

Return strict JSON:
{{
  "title_vi": "Tiêu đề bug tiếng Việt",
  "title_ja": "不具合タイトル（簡潔・中立）",
  "summary_vi": "Tóm tắt",
  "summary_ja": "不具合概要",
  "environment": "Môi trường/build",
  "preconditions": "Tiền điều kiện",
  "steps": ["step 1", "step 2"],
  "expected_result": "...",
  "actual_result": "...",
  "reproduction_rate": "e.g. 5/5 (100%) or 不明",
  "severity_suggestion": "CRITICAL | HIGH | MEDIUM | LOW",
  "notes_ja": "備考 (polite, neutral)"
}}"""
    parsed = await generate_qa_json(prompt, BUG_SYSTEM, preferred_provider, model, max_tokens=2000)
    if not parsed:
        parsed = {
            "title_vi": f"Lỗi: {tc.title if tc else ex.id}",
            "title_ja": f"【不具合】{tc.title if tc else ex.id}",
            "summary_vi": ex.actual_result or "",
            "summary_ja": ex.actual_result or "",
            "environment": f"{run.environment if run else ''} / {run.version_build if run else ''}",
            "preconditions": tc.preconditions if tc else "",
            "steps": ["Thực hiện theo testcase", f"Kết quả thực tế: {ex.actual_result or ''}"],
            "expected_result": tc.expected_result if tc else "",
            "actual_result": ex.actual_result or "",
            "reproduction_rate": "不明",
            "severity_suggestion": "MEDIUM",
            "notes_ja": "ご確認のほどよろしくお願いいたします。",
        }
    parsed["requirement_id"] = ex.requirement_id
    parsed["test_case_id"] = ex.test_case_id
    parsed["test_run_id"] = ex.test_run_id
    parsed["execution_id"] = ex.id
    return parsed


def _bug_details_json(draft: Dict[str, Any], execution_id: str) -> str:
    return json.dumps({
        "title_ja": draft.get("title_ja", ""),
        "summary_vi": draft.get("summary_vi", ""),
        "summary_ja": draft.get("summary_ja", ""),
        "environment": draft.get("environment", ""),
        "preconditions": draft.get("preconditions", ""),
        "steps": draft.get("steps", []),
        "expected_result": draft.get("expected_result", ""),
        "actual_result": draft.get("actual_result", ""),
        "reproduction_rate": draft.get("reproduction_rate", ""),
        "notes_ja": draft.get("notes_ja", ""),
        "execution_id": execution_id,
        "test_run_id": draft.get("test_run_id"),
        "test_case_id": draft.get("test_case_id"),
        "severity_suggestion": draft.get("severity_suggestion", "MEDIUM"),
        "ai_draft": True,
    }, ensure_ascii=False)


async def create_bug_from_execution(
    db: AsyncSession, execution_id: str, draft: Dict[str, Any],
    status: str = "PROPOSED", changed_by: str = "user",
) -> WorkItem:
    ex = await get_execution(db, execution_id)
    if not ex:
        raise ValueError("Execution not found")
    run = (await db.execute(select(TestRun).where(TestRun.id == ex.test_run_id))).scalars().first()
    desc_lines = [
        f"Build: {run.version_build if run else ''} | Env: {run.environment if run else ''} | Run: {run.run_code if run else ''}",
        f"Expected: {draft.get('expected_result', '')}",
        f"Actual: {draft.get('actual_result', '')}",
        f"Repro: {draft.get('reproduction_rate', '')}",
    ]
    bug = WorkItem(
        project_id=run.project_id if run else "",
        item_type="BUG",
        title=(draft.get("title_vi") or draft.get("title_ja") or "Bug")[:255],
        description="\n".join(desc_lines),
        details_json=_bug_details_json(draft, execution_id),
        status=(status or "PROPOSED").upper(),
        priority=(draft.get("severity_suggestion") or "MEDIUM").upper(),
        assignee=None, confidence=0.9,
    )
    if bug.status not in ("PROPOSED", "CONFIRMED", "IN_PROGRESS", "BLOCKED", "DONE", "REJECTED", "SUPERSEDED", "NEEDS_CONFIRMATION", "CONFLICT"):
        bug.status = "PROPOSED"
    db.add(bug)
    await db.flush()
    await ensure_bug_code(db, bug)
    # Evidence: link execution evidence quotes onto the bug
    ev_rows = (await db.execute(
        select(TestEvidence).where(TestEvidence.execution_id == ex.id))).scalars().all()
    for e in ev_rows:
        db.add(WorkItemEvidence(
            work_item_id=bug.id, source_type="test_evidence", source_id=e.id,
            quote_text=f"[{e.evidence_type}] {e.title}: {(e.text_content or e.file_path or '')[:500]}",
            author=changed_by, confirmation_status="PROPOSED",
        ))
        e.bug_work_item_id = bug.id
    tc = (await db.execute(select(TestCase).where(TestCase.id == ex.test_case_id))).scalars().first()
    db.add(WorkItemEvidence(
        work_item_id=bug.id, source_type="test_execution", source_id=ex.id,
        quote_text=f"TC {tc.tc_code if tc else ''} {tc.title if tc else ''} — Expected: {(tc.expected_result if tc else '')[:300]} | Actual: {(ex.actual_result or '')[:300]}",
        author=changed_by, confirmation_status="PROPOSED",
    ))
    # Relationships: bug -> case / execution / requirement / run
    for target_type, target_id, rel in [
        ("test_case", ex.test_case_id, "found_by"),
        ("test_execution", ex.id, "found_in"),
        ("requirement", ex.requirement_id, "found_in"),
        ("test_run", ex.test_run_id, "found_in_run"),
    ]:
        db.add(ProjectRelationship(
            project_id=bug.project_id, source_type="bug", source_id=bug.id,
            target_type=target_type, target_id=target_id, relation_type=rel,
            metadata_json=json.dumps({"execution_id": ex.id}, ensure_ascii=False),
        ))
    ex.bug_work_item_id = bug.id
    await db.flush()
    await log_history(db, ex.id, "bug", None, bug.id, changed_by)
    await refresh_exec_coverage(db, ex.requirement_id)
    await db.commit()
    await db.refresh(bug)
    return bug


# ---------- retest ----------
async def create_retest(db: AsyncSession, execution_id: str,
                        changed_by: str = "user") -> TestExecution:
    src = await get_execution(db, execution_id)
    if not src:
        raise ValueError("Execution not found")
    if src.status != "FAIL":
        raise ValueError("Only FAIL executions can spawn a retest.")
    new_ex = TestExecution(
        test_run_id=src.test_run_id, test_case_id=src.test_case_id,
        requirement_id=src.requirement_id,
        acceptance_criterion_id=src.acceptance_criterion_id,
        attempt_no=src.attempt_no + 1, prev_execution_id=src.id,
        status="NOT_RUN", bug_work_item_id=src.bug_work_item_id,
        case_snapshot_json=src.case_snapshot_json,
    )
    db.add(new_ex)
    await db.flush()
    await log_history(db, src.id, "retest", src.id, new_ex.id, changed_by)
    # Mark linked bug as RETEST intent (details flag, WorkItem status -> IN_PROGRESS)
    if src.bug_work_item_id:
        bug = (await db.execute(
            select(WorkItem).where(WorkItem.id == src.bug_work_item_id))).scalars().first()
        if bug:
            try:
                d = json.loads(bug.details_json or "{}")
            except Exception:
                d = {}
            d["qa_retest"] = True
            d["retest_execution_id"] = new_ex.id
            bug.details_json = json.dumps(d, ensure_ascii=False)
            if bug.status == "DONE":
                bug.status = "IN_PROGRESS"
            await db.flush()
    await db.commit()
    await db.refresh(new_ex)
    return new_ex


# ---------- execution coverage (§18) ----------
async def refresh_exec_coverage(db: AsyncSession, requirement_id: str) -> RequirementCoverage:
    cov = (await db.execute(
        select(RequirementCoverage).where(RequirementCoverage.requirement_id == requirement_id)
    )).scalars().first()
    if not cov:
        try:
            cov = await E1.refresh_coverage(db, requirement_id)
        except ValueError:
            raise
    rows = (await db.execute(select(TestExecution).where(
        TestExecution.requirement_id == requirement_id))).scalars().all()
    # Latest attempt per test case wins
    latest: Dict[str, TestExecution] = {}
    for r in rows:
        cur = latest.get(r.test_case_id)
        if not cur or r.attempt_no > cur.attempt_no:
            latest[r.test_case_id] = r
    vals = list(latest.values())
    cov.exec_total = len(vals)
    cov.exec_executed = sum(1 for r in vals if r.status in ("PASS", "FAIL", "BLOCKED", "SKIPPED"))
    cov.exec_passed = sum(1 for r in vals if r.status == "PASS")
    cov.exec_failed = sum(1 for r in vals if r.status == "FAIL")
    cov.exec_blocked = sum(1 for r in vals if r.status == "BLOCKED")
    if not vals:
        cov.exec_status = "Designed"
    elif any(r.status == "FAIL" for r in vals):
        cov.exec_status = "Failed"
    elif any(r.status == "BLOCKED" for r in vals):
        cov.exec_status = "Blocked"
    elif all(r.status == "PASS" for r in vals):
        cov.exec_status = "Passed"
    else:
        cov.exec_status = "NotExecuted"
    # last result/build from most recent execution
    if vals:
        ordered = sorted(vals, key=lambda r: r.updated_at or r.created_at, reverse=True)
        cov.last_result = ordered[0].status
        run = (await db.execute(
            select(TestRun).where(TestRun.id == ordered[0].test_run_id))).scalars().first()
        cov.last_build = run.version_build if run else None
    await db.flush()
    return cov


# ---------- reports (§19-22, evidence only, never release verdict) ----------
async def build_run_metrics(db: AsyncSession, run_id: str) -> Dict[str, Any]:
    run = (await db.execute(select(TestRun).where(TestRun.id == run_id))).scalars().first()
    if not run:
        raise ValueError("Test run not found")
    prog = await run_progress(db, run_id)
    ex_rows = (await db.execute(select(TestExecution).where(
        TestExecution.test_run_id == run_id))).scalars().all()
    bug_ids = sorted({e.bug_work_item_id for e in ex_rows if e.bug_work_item_id})
    bugs = []
    if bug_ids:
        bugs = (await db.execute(select(WorkItem).where(WorkItem.id.in_(bug_ids)))).scalars().all()
    open_bugs = [b for b in bugs if b.status not in ("DONE", "SUPERSEDED", "REJECTED")]
    # untested scope: requirements with cases in run but no executed attempt
    req_ids = sorted({e.requirement_id for e in ex_rows})
    untested_reqs: List[str] = []
    for rid in req_ids:
        sts = [e.status for e in ex_rows if e.requirement_id == rid]
        if not any(s in ("PASS", "FAIL", "BLOCKED", "SKIPPED") for s in sts):
            req_item = await E1.get_requirement(db, rid)
            untested_reqs.append(f"{getattr(req_item, 'req_code', '')} {req_item.title if req_item else rid}")
    # pending questions (project-wide, unanswered)
    from app.qa.models import QAOpenQuestion
    pend_q_stmt = select(func.count(QAOpenQuestion.id)).where(
        QAOpenQuestion.project_id == run.project_id,
        QAOpenQuestion.status.in_(["DRAFT", "APPROVED"]))
    pend_q = (await db.execute(pend_q_stmt)).scalar() or 0
    # failures detail
    failures = []
    for e in ex_rows:
        if e.status in ("FAIL", "BLOCKED"):
            tc = (await db.execute(select(TestCase).where(TestCase.id == e.test_case_id))).scalars().first()
            failures.append({
                "tc_code": tc.tc_code if tc else "", "title": tc.title if tc else "",
                "status": e.status, "actual": (e.actual_result or "")[:300],
                "bug_id": e.bug_work_item_id,
            })
    return {
        "run_id": run.id, "run_code": run.run_code, "run_name": run.name,
        "build": run.version_build, "environment": run.environment,
        "tester": run.tester, "run_status": run.status,
        "total": prog["total"], "executed": prog["executed"],
        "passed": prog["pass"], "failed": prog["fail"],
        "blocked": prog["blocked"], "skipped": prog["skipped"], "not_run": prog["not_run"],
        "open_bugs": [{"id": b.id, "code": b.req_code, "title": b.title, "status": b.status,
                       "ux_status": bug_ux_status(b.status, b.details_json)} for b in open_bugs],
        "open_bug_count": len(open_bugs),
        "failures": failures,
        "untested_scope": untested_reqs,
        "pending_questions": pend_q,
    }


REPORT_SYSTEM = (
    "You are a senior QA lead writing a factual QA report for a Japanese project. "
    "Present evidence and numbers only. NEVER conclude the release is safe or production-ready. "
    "Release decisions belong to humans. Write both Vietnamese and Japanese (polite neutral keigo)."
)


async def draft_report(
    db: AsyncSession, run_id: str, report_type: str = "summary",
    preferred_provider: Optional[str] = None, model: Optional[str] = None,
    created_by: str = "user",
) -> QAReport:
    metrics = await build_run_metrics(db, run_id)
    run = (await db.execute(select(TestRun).where(TestRun.id == run_id))).scalars().first()
    kind_label = {"summary": "QA Summary", "completion": "Test Completion Report", "daily": "Daily QA Status"}.get(report_type, "QA Summary")
    prompt = f"""Write a {kind_label} from these factual metrics. Numbers must match exactly.

Metrics:
{json.dumps(metrics, ensure_ascii=False)[:4000]}

Structure (both languages):
- Scope / Build / Environment
- Execution summary (total/executed/passed/failed/blocked/not run)
- Failed cases, open bugs, blocked cases
- Untested scope, pending questions, known risks (list facts only)
- Notes

Rules: do NOT say the release is safe/ready. End risks as factual bullets.
Return strict JSON: {{"markdown_vi": "...", "markdown_ja": "..."}}"""
    parsed = await generate_qa_json(prompt, REPORT_SYSTEM, preferred_provider, model, max_tokens=2500)
    md_vi = parsed.get("markdown_vi", "") if parsed else ""
    md_ja = parsed.get("markdown_ja", "") if parsed else ""
    if not md_vi:
        m = metrics
        md_vi = (
            f"# {kind_label} — {m['run_name']} ({m['build']})\n\n"
            f"- Môi trường: {m['environment']} | Tester: {m['tester']}\n"
            f"- Tổng: {m['total']} | Đã chạy: {m['executed']} | PASS: {m['passed']} | "
            f"FAIL: {m['failed']} | BLOCKED: {m['blocked']} | Chưa chạy: {m['not_run']}\n"
            f"- Bug mở: {m['open_bug_count']} | Câu hỏi pending: {m['pending_questions']}\n"
            f"- Phạm vi chưa test: {', '.join(m['untested_scope']) or '—'}\n"
        )
    if not md_ja:
        m = metrics
        md_ja = (
            f"# {kind_label} — {m['run_name']} ({m['build']})\n\n"
            f"- 環境: {m['environment']} | 担当: {m['tester']}\n"
            f"- 合計: {m['total']} | 実行済: {m['executed']} | PASS: {m['passed']} | "
            f"FAIL: {m['failed']} | BLOCKED: {m['blocked']} | 未実行: {m['not_run']}\n"
            f"- 未解決の不具合: {m['open_bug_count']} | 未回答の質問: {m['pending_questions']}\n"
        )
    report = QAReport(
        project_id=run.project_id, test_run_id=run_id, report_type=report_type,
        scope_build=run.version_build or "", markdown_vi=md_vi, markdown_ja=md_ja,
        metrics_json=json.dumps(metrics, ensure_ascii=False),
        status="DRAFT", ai_generated=True, created_by=created_by,
    )
    db.add(report)
    await db.flush()
    await db.commit()
    await db.refresh(report)
    return report
