"""QA Workspace Phase 1 REST API (prefix /api/qa)."""
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.intelligence.models import WorkItem
from app.qa.models import (
    QAFinding, QAOpenQuestion, AcceptanceCriterion, TestCase, TestStep, RequirementCoverage,
)
from app.qa import schemas as S
from app.qa import engines as E

router = APIRouter(prefix="/api/qa", tags=["QA Workspace"])


# ---------- serializers ----------
def _ts(v) -> str:
    try:
        return v.isoformat() if v else ""
    except Exception:
        return ""


def ser_finding(f: QAFinding) -> dict:
    return {"id": f.id, "project_id": f.project_id, "requirement_id": f.requirement_id,
            "title": f.title, "description": f.description or "", "finding_type": f.finding_type,
            "severity": f.severity, "confidence": f.confidence,
            "evidence_quote": f.evidence_quote or "", "evidence_source_type": f.evidence_source_type or "",
            "evidence_source_id": f.evidence_source_id or "", "knowledge_class": f.knowledge_class,
            "suggested_action": f.suggested_action, "status": f.status,
            "ai_generated": f.ai_generated, "created_at": _ts(f.created_at), "updated_at": _ts(f.updated_at)}


def ser_question(q: QAOpenQuestion) -> dict:
    return {"id": q.id, "project_id": q.project_id, "requirement_id": q.requirement_id,
            "finding_id": q.finding_id, "question_vi": q.question_vi, "question_ja": q.question_ja or "",
            "reason": q.reason or "", "evidence_quote": q.evidence_quote or "",
            "risk_if_unanswered": q.risk_if_unanswered, "status": q.status,
            "answer_text": q.answer_text, "ai_generated": q.ai_generated,
            "created_at": _ts(q.created_at), "updated_at": _ts(q.updated_at)}


def ser_ac(a: AcceptanceCriterion) -> dict:
    return {"id": a.id, "project_id": a.project_id, "requirement_id": a.requirement_id,
            "ac_code": a.ac_code or "", "given_text": a.given_text or "",
            "when_text": a.when_text or "", "then_text": a.then_text or "",
            "knowledge_class": a.knowledge_class, "evidence_quote": a.evidence_quote or "",
            "status": a.status, "ai_generated": a.ai_generated,
            "created_at": _ts(a.created_at), "updated_at": _ts(a.updated_at)}


def ser_step(s: TestStep) -> dict:
    return {"id": s.id, "step_order": s.step_order, "action": s.action, "expected": s.expected or ""}


def ser_case(tc: TestCase) -> dict:
    steps = [ser_step(s) for s in sorted((tc.steps or []), key=lambda x: x.step_order)]
    return {"id": tc.id, "project_id": tc.project_id, "tc_code": tc.tc_code or "",
            "title": tc.title, "purpose": tc.purpose or "", "case_type": tc.case_type,
            "priority": tc.priority, "preconditions": tc.preconditions or "",
            "expected_result": tc.expected_result or "", "requirement_id": tc.requirement_id,
            "acceptance_criterion_id": tc.acceptance_criterion_id,
            "evidence_quote": tc.evidence_quote or "", "knowledge_class": tc.knowledge_class,
            "source": tc.source, "ai_generated": tc.ai_generated, "confidence": tc.confidence,
            "status": tc.status, "steps": steps,
            "created_at": _ts(tc.created_at), "updated_at": _ts(tc.updated_at)}


async def _require_req(db: AsyncSession, requirement_id: str) -> WorkItem:
    item = await E.get_requirement(db, requirement_id)
    if not item or item.item_type != "REQUIREMENT":
        raise HTTPException(status_code=404, detail="Requirement not found")
    return item


# ---------- Review ----------
@router.post("/requirements/{requirement_id}/review", response_model=List[S.FindingResponse])
async def review_requirement(requirement_id: str, payload: S.ReviewRequest, db: AsyncSession = Depends(get_db)):
    await _require_req(db, requirement_id)
    try:
        findings = await E.review_requirement(
            db, requirement_id, payload.preferred_provider, payload.model, payload.force)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return [ser_finding(f) for f in findings]


@router.get("/requirements/{requirement_id}/findings", response_model=List[S.FindingResponse])
async def list_findings(requirement_id: str, db: AsyncSession = Depends(get_db)):
    await _require_req(db, requirement_id)
    res = await db.execute(select(QAFinding).where(QAFinding.requirement_id == requirement_id).order_by(QAFinding.created_at))
    return [ser_finding(f) for f in res.scalars().all()]


@router.patch("/findings/{finding_id}", response_model=S.FindingResponse)
async def update_finding(finding_id: str, payload: S.FindingStatusUpdate, db: AsyncSession = Depends(get_db)):
    f = (await db.execute(select(QAFinding).where(QAFinding.id == finding_id))).scalars().first()
    if not f:
        raise HTTPException(status_code=404, detail="Finding not found")
    if payload.status.upper() not in ("OPEN", "RESOLVED", "IGNORED"):
        raise HTTPException(status_code=400, detail="Invalid status")
    f.status = payload.status.upper()
    await db.flush()
    await E.refresh_coverage(db, f.requirement_id)
    await db.commit()
    await db.refresh(f)
    return ser_finding(f)


# ---------- Questions ----------
@router.post("/requirements/{requirement_id}/questions:generate", response_model=List[S.OpenQuestionResponse])
async def generate_questions(requirement_id: str, payload: S.GenerateQuestionsRequest, db: AsyncSession = Depends(get_db)):
    await _require_req(db, requirement_id)
    try:
        questions = await E.generate_questions(
            db, requirement_id, payload.finding_ids, payload.preferred_provider, payload.model)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return [ser_question(q) for q in questions]


@router.get("/requirements/{requirement_id}/questions", response_model=List[S.OpenQuestionResponse])
async def list_questions(requirement_id: str, db: AsyncSession = Depends(get_db)):
    await _require_req(db, requirement_id)
    res = await db.execute(select(QAOpenQuestion).where(QAOpenQuestion.requirement_id == requirement_id).order_by(QAOpenQuestion.created_at))
    return [ser_question(q) for q in res.scalars().all()]


@router.patch("/questions/{question_id}", response_model=S.OpenQuestionResponse)
async def update_question(question_id: str, payload: S.OpenQuestionUpdate, db: AsyncSession = Depends(get_db)):
    q = (await db.execute(select(QAOpenQuestion).where(QAOpenQuestion.id == question_id))).scalars().first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    for field in ("question_vi", "question_ja", "reason", "risk_if_unanswered", "answer_text"):
        v = getattr(payload, field)
        if v is not None:
            setattr(q, field, v)
    if payload.status is not None:
        if payload.status.upper() not in ("DRAFT", "APPROVED", "ANSWERED", "REJECTED"):
            raise HTTPException(status_code=400, detail="Invalid status")
        q.status = payload.status.upper()
    await db.flush()
    await E.refresh_coverage(db, q.requirement_id)
    await db.commit()
    await db.refresh(q)
    return ser_question(q)


# ---------- Acceptance Criteria ----------
@router.post("/requirements/{requirement_id}/acceptance-criteria:generate",
             response_model=List[S.AcceptanceCriterionResponse])
async def generate_ac(requirement_id: str, payload: S.ProviderSelection, db: AsyncSession = Depends(get_db)):
    item = await _require_req(db, requirement_id)
    cov = (await db.execute(
        select(RequirementCoverage).where(RequirementCoverage.requirement_id == requirement_id))).scalars().first()
    blocked = bool(cov and cov.status == "BlockedByClarification")
    try:
        criteria = await E.generate_acceptance_criteria(db, requirement_id, payload.preferred_provider, payload.model)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    out = [ser_ac(c) for c in criteria]
    if blocked:
        for o in out:
            o["knowledge_class"] = o["knowledge_class"]  # unchanged; flag via detail endpoint
    return out


@router.get("/requirements/{requirement_id}/acceptance-criteria", response_model=List[S.AcceptanceCriterionResponse])
async def list_ac(requirement_id: str, db: AsyncSession = Depends(get_db)):
    await _require_req(db, requirement_id)
    res = await db.execute(select(AcceptanceCriterion).where(
        AcceptanceCriterion.requirement_id == requirement_id).order_by(AcceptanceCriterion.ac_code))
    return [ser_ac(a) for a in res.scalars().all()]


@router.post("/requirements/{requirement_id}/acceptance-criteria", response_model=S.AcceptanceCriterionResponse)
async def create_ac(requirement_id: str, payload: S.AcceptanceCriterionCreate, db: AsyncSession = Depends(get_db)):
    item = await _require_req(db, requirement_id)
    count = (await db.execute(select(func.count(AcceptanceCriterion.id)).where(
        AcceptanceCriterion.requirement_id == requirement_id))).scalar() or 0
    a = AcceptanceCriterion(project_id=item.project_id, requirement_id=requirement_id,
                            ac_code=f"AC-{count + 1:03d}", given_text=payload.given_text,
                            when_text=payload.when_text, then_text=payload.then_text,
                            knowledge_class="Confirmed", evidence_quote=payload.evidence_quote or item.title,
                            status="DRAFT", ai_generated=False)
    db.add(a)
    await db.flush()
    await E.refresh_coverage(db, requirement_id)
    await db.commit()
    await db.refresh(a)
    return ser_ac(a)


@router.patch("/acceptance-criteria/{ac_id}", response_model=S.AcceptanceCriterionResponse)
async def update_ac(ac_id: str, payload: S.AcceptanceCriterionUpdate, db: AsyncSession = Depends(get_db)):
    a = (await db.execute(select(AcceptanceCriterion).where(AcceptanceCriterion.id == ac_id))).scalars().first()
    if not a:
        raise HTTPException(status_code=404, detail="Acceptance criterion not found")
    for field in ("given_text", "when_text", "then_text"):
        v = getattr(payload, field)
        if v is not None:
            setattr(a, field, v)
    if payload.status is not None:
        if payload.status.upper() not in ("DRAFT", "APPROVED", "REJECTED"):
            raise HTTPException(status_code=400, detail="Invalid status")
        a.status = payload.status.upper()
    await db.flush()
    await E.refresh_coverage(db, a.requirement_id)
    await db.commit()
    await db.refresh(a)
    return ser_ac(a)


@router.delete("/acceptance-criteria/{ac_id}")
async def delete_ac(ac_id: str, db: AsyncSession = Depends(get_db)):
    a = (await db.execute(select(AcceptanceCriterion).where(AcceptanceCriterion.id == ac_id))).scalars().first()
    if not a:
        raise HTTPException(status_code=404, detail="Acceptance criterion not found")
    req_id = a.requirement_id
    await db.delete(a)
    await db.flush()
    await E.refresh_coverage(db, req_id)
    await db.commit()
    return {"status": "deleted", "id": ac_id}


# ---------- Test Cases ----------
@router.post("/requirements/{requirement_id}/test-cases:generate", response_model=List[S.TestCaseResponse])
async def generate_cases(requirement_id: str, payload: S.GenerateTestCasesRequest, db: AsyncSession = Depends(get_db)):
    await _require_req(db, requirement_id)
    try:
        cases = await E.generate_test_cases(
            db, requirement_id, payload.acceptance_criterion_ids, payload.checklist_mode,
            payload.preferred_provider, payload.model)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    out = []
    for tc in cases:
        await db.refresh(tc, attribute_names=["steps"])
        out.append(ser_case(tc))
    return out


@router.post("/requirements/{requirement_id}/test-cases", response_model=S.TestCaseResponse)
async def create_case(requirement_id: str, payload: S.TestCaseCreate, db: AsyncSession = Depends(get_db)):
    item = await _require_req(db, requirement_id)
    start_n = await E._next_tc_number(db, item.project_id)
    tc = TestCase(project_id=item.project_id, tc_code=f"TC-{start_n:03d}", title=payload.title[:255],
                  purpose=payload.purpose, case_type=payload.case_type or "Happy",
                  priority=(payload.priority or "MEDIUM").upper(), preconditions=payload.preconditions,
                  expected_result=payload.expected_result, requirement_id=requirement_id,
                  acceptance_criterion_id=payload.acceptance_criterion_id,
                  evidence_quote=payload.evidence_quote or item.title,
                  knowledge_class="Confirmed", source="Manual", ai_generated=False,
                  confidence=1.0, status="DRAFT")
    db.add(tc)
    await db.flush()
    order = 0
    for s in (payload.steps or []):
        order += 1
        db.add(TestStep(test_case_id=tc.id, step_order=order, action=s.action, expected=s.expected))
    if order == 0:
        db.add(TestStep(test_case_id=tc.id, step_order=1, action=f"Execute: {payload.title}",
                        expected=payload.expected_result or "Expected behavior observed."))
    await E.refresh_coverage(db, requirement_id)
    await db.commit()
    await db.refresh(tc, attribute_names=["steps"])
    return ser_case(tc)


@router.get("/test-cases", response_model=List[S.TestCaseResponse])
async def list_cases(project_id: Optional[str] = None, requirement_id: Optional[str] = None,
                     case_type: Optional[str] = None, priority: Optional[str] = None,
                     status: Optional[str] = None, search: Optional[str] = None,
                     db: AsyncSession = Depends(get_db)):
    stmt = select(TestCase).options(selectinload(TestCase.steps)).order_by(desc(TestCase.created_at))
    if project_id:
        stmt = stmt.where(TestCase.project_id == project_id)
    if requirement_id:
        stmt = stmt.where(TestCase.requirement_id == requirement_id)
    if case_type:
        stmt = stmt.where(TestCase.case_type == case_type)
    if priority:
        stmt = stmt.where(TestCase.priority == priority.upper())
    if status:
        stmt = stmt.where(TestCase.status == status.upper())
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(TestCase.title.like(like), TestCase.purpose.like(like), TestCase.tc_code.like(like)))
    res = await db.execute(stmt.limit(300))
    return [ser_case(tc) for tc in res.scalars().all()]


@router.get("/test-cases/{case_id}", response_model=S.TestCaseResponse)
async def get_case(case_id: str, db: AsyncSession = Depends(get_db)):
    tc = (await db.execute(select(TestCase).options(selectinload(TestCase.steps)).where(TestCase.id == case_id))).scalars().first()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    return ser_case(tc)


@router.patch("/test-cases/{case_id}", response_model=S.TestCaseResponse)
async def update_case(case_id: str, payload: S.TestCaseUpdate, db: AsyncSession = Depends(get_db)):
    tc = (await db.execute(select(TestCase).options(selectinload(TestCase.steps)).where(TestCase.id == case_id))).scalars().first()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    for field in ("title", "purpose", "case_type", "priority", "preconditions",
                  "expected_result", "acceptance_criterion_id"):
        v = getattr(payload, field)
        if v is not None:
            setattr(tc, field, v.upper() if field == "priority" and isinstance(v, str) else v)
    if payload.status is not None:
        if payload.status.upper() not in ("DRAFT", "REVIEWED", "APPROVED", "REJECTED"):
            raise HTTPException(status_code=400, detail="Invalid status")
        tc.status = payload.status.upper()
    if payload.steps is not None:
        for s in list(tc.steps or []):
            await db.delete(s)
        await db.flush()
        for i, s in enumerate(payload.steps):
            db.add(TestStep(test_case_id=tc.id, step_order=i + 1, action=s.action, expected=s.expected))
    await db.flush()
    await E.refresh_coverage(db, tc.requirement_id)
    await db.commit()
    await db.refresh(tc, attribute_names=["steps"])
    return ser_case(tc)


@router.post("/test-cases/{case_id}/duplicate", response_model=S.TestCaseResponse)
async def duplicate_case(case_id: str, db: AsyncSession = Depends(get_db)):
    src = (await db.execute(select(TestCase).options(selectinload(TestCase.steps)).where(TestCase.id == case_id))).scalars().first()
    if not src:
        raise HTTPException(status_code=404, detail="Test case not found")
    start_n = await E._next_tc_number(db, src.project_id)
    tc = TestCase(project_id=src.project_id, tc_code=f"TC-{start_n:03d}", title=f"[Copy] {src.title}"[:255],
                  purpose=src.purpose, case_type=src.case_type, priority=src.priority,
                  preconditions=src.preconditions, expected_result=src.expected_result,
                  requirement_id=src.requirement_id, acceptance_criterion_id=src.acceptance_criterion_id,
                  evidence_quote=src.evidence_quote, knowledge_class=src.knowledge_class,
                  source="Manual", ai_generated=False, confidence=src.confidence, status="DRAFT")
    db.add(tc)
    await db.flush()
    for s in sorted((src.steps or []), key=lambda x: x.step_order):
        db.add(TestStep(test_case_id=tc.id, step_order=s.step_order, action=s.action, expected=s.expected))
    await E.refresh_coverage(db, tc.requirement_id)
    await db.commit()
    await db.refresh(tc, attribute_names=["steps"])
    return ser_case(tc)


@router.delete("/test-cases/{case_id}")
async def delete_case(case_id: str, db: AsyncSession = Depends(get_db)):
    tc = (await db.execute(select(TestCase).where(TestCase.id == case_id))).scalars().first()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    req_id = tc.requirement_id
    await db.delete(tc)
    await db.flush()
    await E.refresh_coverage(db, req_id)
    await db.commit()
    return {"status": "deleted", "id": case_id}


# ---------- Requirement Detail aggregate (§14) ----------
@router.get("/requirements/{requirement_id}/detail", response_model=S.RequirementDetailResponse)
async def requirement_detail(requirement_id: str, db: AsyncSession = Depends(get_db)):
    item = await _require_req(db, requirement_id)
    await E.ensure_req_code(db, item)
    await db.commit()
    findings = (await db.execute(select(QAFinding).where(QAFinding.requirement_id == requirement_id))).scalars().all()
    questions = (await db.execute(select(QAOpenQuestion).where(QAOpenQuestion.requirement_id == requirement_id))).scalars().all()
    acs = (await db.execute(select(AcceptanceCriterion).where(
        AcceptanceCriterion.requirement_id == requirement_id).order_by(AcceptanceCriterion.ac_code))).scalars().all()
    cases = (await db.execute(select(TestCase).options(selectinload(TestCase.steps)).where(
        TestCase.requirement_id == requirement_id).order_by(TestCase.tc_code))).scalars().all()
    cov = (await db.execute(select(RequirementCoverage).where(
        RequirementCoverage.requirement_id == requirement_id))).scalars().first()
    cov_out = None
    if cov:
        cov_out = {"project_id": cov.project_id, "requirement_id": cov.requirement_id,
                   "requirement_title": item.title, "req_code": item.req_code,
                   "has_review": cov.has_review, "findings_open": cov.findings_open,
                   "questions_unanswered": cov.questions_unanswered, "ac_total": cov.ac_total,
                   "ac_approved": cov.ac_approved, "tc_total": cov.tc_total,
                   "tc_approved": cov.tc_approved, "status": cov.status, "computed_at": _ts(cov.computed_at)}
    # --- Phase 2: latest test result + related bugs + execution coverage ---
    from app.qa.execution_models import TestRun, TestExecution
    from app.qa import execution_engines as X2
    cov2 = await X2.refresh_exec_coverage(db, requirement_id)
    await db.commit()
    ex_rows = (await db.execute(select(TestExecution).where(
        TestExecution.requirement_id == requirement_id).order_by(desc(TestExecution.updated_at)).limit(50)
    )).scalars().all()
    bug_map: dict = {}
    for e in ex_rows:
        if e.bug_work_item_id and e.bug_work_item_id not in bug_map:
            b = (await db.execute(select(WorkItem).where(
                WorkItem.id == e.bug_work_item_id))).scalars().first()
            if b:
                bug_map[b.id] = {"id": b.id, "bug_code": b.req_code, "title": b.title,
                                 "status": b.status,
                                 "ux_status": X2.bug_ux_status(b.status, b.details_json)}
    # per-case history: latest attempt per case with build
    hist_by_case: dict = {}
    for e in sorted(ex_rows, key=lambda x: (x.attempt_no or 0)):
        run = (await db.execute(select(TestRun).where(TestRun.id == e.test_run_id))).scalars().first()
        tc = next((c for c in cases if c.id == e.test_case_id), None)
        hist_by_case[e.test_case_id] = {
            "tc_code": tc.tc_code if tc else "", "status": e.status,
            "attempt_no": e.attempt_no, "build": run.version_build if run else "",
            "run_code": run.run_code if run else "",
            "bug_code": bug_map.get(e.bug_work_item_id, {}).get("bug_code") if e.bug_work_item_id else None,
        }
    exec_summary = {
        "exec_total": cov2.exec_total, "exec_executed": cov2.exec_executed,
        "exec_passed": cov2.exec_passed, "exec_failed": cov2.exec_failed,
        "exec_blocked": cov2.exec_blocked, "exec_status": cov2.exec_status,
        "last_result": cov2.last_result, "last_build": cov2.last_build,
    }
    return {"id": item.id, "project_id": item.project_id, "req_code": item.req_code,
            "title": item.title, "description": item.description or "",
            "status": item.status, "priority": item.priority,
            "evidence_items": [{"id": e.id, "source_type": e.source_type, "source_id": e.source_id,
                                "quote_text": e.quote_text, "author": e.author,
                                "timestamp": e.timestamp, "confidence": e.confidence,
                                "confirmation_status": e.confirmation_status}
                               for e in (item.evidence_items or [])],
            "findings": [ser_finding(f) for f in findings],
            "questions": [ser_question(q) for q in questions],
            "acceptance_criteria": [ser_ac(a) for a in acs],
            "test_cases": [ser_case(tc) for tc in cases],
            "coverage": cov_out,
            "exec_summary": exec_summary,
            "related_bugs": list(bug_map.values()),
            "case_history": list(hist_by_case.values())}


# ---------- Requirements list w/ coverage ----------
@router.get("/projects/{project_id}/requirements")
async def qa_requirements(project_id: str, status: Optional[str] = None,
                          coverage: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(WorkItem).options(selectinload(WorkItem.evidence_items)).where(
        WorkItem.project_id == project_id, WorkItem.item_type == "REQUIREMENT",
    ).order_by(desc(WorkItem.created_at))
    if status:
        stmt = stmt.where(WorkItem.status == status.upper())
    items = (await db.execute(stmt)).scalars().all()
    cov_rows = (await db.execute(select(RequirementCoverage).where(
        RequirementCoverage.project_id == project_id))).scalars().all()
    cov_by_req = {c.requirement_id: c for c in cov_rows}
    out = []
    for it in items:
        if not it.req_code:
            await E.ensure_req_code(db, it)
        c = cov_by_req.get(it.id)
        cov_status = c.status if c else "NotReviewed"
        if coverage and cov_status != coverage:
            continue
        out.append({"id": it.id, "project_id": it.project_id, "req_code": it.req_code,
                    "title": it.title, "description": (it.description or "")[:300],
                    "status": it.status, "priority": it.priority,
                    "evidence_count": len(it.evidence_items or []),
                    "coverage": cov_status,
                    "findings_open": c.findings_open if c else 0,
                    "questions_unanswered": c.questions_unanswered if c else 0,
                    "ac_total": c.ac_total if c else 0, "tc_total": c.tc_total if c else 0})
    await db.commit()
    return out


# ---------- Coverage ----------
@router.get("/projects/{project_id}/coverage", response_model=List[S.CoverageResponse])
async def project_coverage(project_id: str, db: AsyncSession = Depends(get_db)):
    items = (await db.execute(select(WorkItem).where(
        WorkItem.project_id == project_id, WorkItem.item_type == "REQUIREMENT"))).scalars().all()
    out = []
    for it in items:
        cov = await E.refresh_coverage(db, it.id)
        out.append({"project_id": project_id, "requirement_id": it.id,
                    "requirement_title": it.title, "req_code": it.req_code,
                    "has_review": cov.has_review, "findings_open": cov.findings_open,
                    "questions_unanswered": cov.questions_unanswered, "ac_total": cov.ac_total,
                    "ac_approved": cov.ac_approved, "tc_total": cov.tc_total,
                    "tc_approved": cov.tc_approved, "status": cov.status,
                    "computed_at": _ts(cov.computed_at)})
    await db.commit()
    return out


@router.get("/projects/{project_id}/overview", response_model=S.QAOverviewResponse)
async def qa_overview(project_id: str, db: AsyncSession = Depends(get_db)):
    from app.qa.regression_models import ChangeRecord, RegressionPlan
    from app.qa.regression.plan_engine import plan_change_ids  # noqa

    async def _phase5_overview_counts(db: AsyncSession, eff):
        def _f(stmt, model):
            return stmt.where(model.project_id == eff) if eff else stmt
        pending = (await db.execute(_f(select(func.count(ChangeRecord.id)).where(
            ChangeRecord.status == "DRAFT"), ChangeRecord))).scalar() or 0
        plans_req = (await db.execute(_f(select(func.count(RegressionPlan.id)).where(
            RegressionPlan.status.in_(["DRAFT", "REVIEWED"])), RegressionPlan))).scalar() or 0
        plans_run = (await db.execute(_f(select(func.count(RegressionPlan.id)).where(
            RegressionPlan.test_run_id.isnot(None)), RegressionPlan))).scalar() or 0
        high_risk = (await db.execute(_f(select(func.count(ChangeRecord.id)).where(
            ChangeRecord.risk_level.in_(["CRITICAL", "HIGH"])), ChangeRecord))).scalar() or 0
        needs_update = 0
        try:
            from app.qa.ui_models import UIAutomationScript
            from app.qa.api_models import APITestConfig as _AC
            if eff:
                ui_q = select(func.count(UIAutomationScript.test_case_id)).join(
                    TestCase, TestCase.id == UIAutomationScript.test_case_id).where(
                    TestCase.project_id == eff,
                    UIAutomationScript.status == "NEEDS_UPDATE")
                api_q = select(func.count(_AC.test_case_id)).join(
                    TestCase, TestCase.id == _AC.test_case_id).where(
                    TestCase.project_id == eff, _AC.outdated_flag == True)
            else:
                ui_q = select(func.count(UIAutomationScript.test_case_id)).where(
                    UIAutomationScript.status == "NEEDS_UPDATE")
                api_q = select(func.count(_AC.test_case_id)).where(_AC.outdated_flag == True)
            needs_update = ((await db.execute(ui_q)).scalar() or 0) + \
                ((await db.execute(api_q)).scalar() or 0)
        except Exception:
            pass
        return {"changes_pending": pending, "regression_required": plans_req,
                "regression_in_progress": plans_run, "high_risk_changes": high_risk,
                "tests_needing_update": needs_update}

    eff = project_id if project_id not in ("all", "") else None
    def _w(stmt, model=WorkItem, pid_field="project_id"):
        if eff:
            stmt = stmt.where(getattr(model, pid_field) == eff)
        return stmt
    total_req = (await db.execute(_w(select(func.count(WorkItem.id)).where(WorkItem.item_type == "REQUIREMENT")))).scalar() or 0
    reviewed = (await db.execute(_w(
        select(func.count(RequirementCoverage.requirement_id)).where(RequirementCoverage.has_review == True),
        RequirementCoverage))).scalar() or 0
    blocked = (await db.execute(_w(
        select(func.count(RequirementCoverage.requirement_id)).where(
            RequirementCoverage.status == "BlockedByClarification"), RequirementCoverage))).scalar() or 0
    open_q = (await db.execute(_w(select(func.count(QAOpenQuestion.id)).where(
        QAOpenQuestion.status.in_(["DRAFT", "APPROVED"])), QAOpenQuestion))).scalar() or 0
    unapproved_ac = (await db.execute(_w(select(func.count(AcceptanceCriterion.id)).where(
        AcceptanceCriterion.status == "DRAFT"), AcceptanceCriterion))).scalar() or 0
    covered = (await db.execute(_w(
        select(func.count(RequirementCoverage.requirement_id)).where(RequirementCoverage.status == "Covered"),
        RequirementCoverage))).scalar() or 0
    uncovered = (await db.execute(_w(
        select(func.count(RequirementCoverage.requirement_id)).where(
            RequirementCoverage.status.in_(["NotCovered", "PartiallyCovered", "NotReviewed"])),
        RequirementCoverage))).scalar() or 0
    tc_draft = (await db.execute(_w(select(func.count(TestCase.id)).where(
        TestCase.status.in_(["DRAFT", "REVIEWED"])), TestCase))).scalar() or 0
    tc_approved = (await db.execute(_w(select(func.count(TestCase.id)).where(
        TestCase.status == "APPROVED"), TestCase))).scalar() or 0
    # --- Phase 2 additions (lazy import avoids circulars) ---
    from app.qa.execution_models import TestRun, TestExecution
    active_runs = (await db.execute(_w(select(func.count(TestRun.id)).where(
        TestRun.status.in_(["READY", "IN_PROGRESS"])), TestRun))).scalar() or 0

    def _exec_count(status_values):
        stmt = select(func.count(TestExecution.id)).join(
            TestRun, TestExecution.test_run_id == TestRun.id).where(
            TestExecution.status.in_(status_values))
        if eff:
            stmt = stmt.where(TestRun.project_id == eff)
        return stmt
    exec_pass = (await db.execute(_exec_count(["PASS"]))).scalar() or 0
    exec_fail = (await db.execute(_exec_count(["FAIL"]))).scalar() or 0
    exec_blocked = (await db.execute(_exec_count(["BLOCKED"]))).scalar() or 0
    exec_not_run = (await db.execute(_exec_count(["NOT_RUN", "RUNNING"]))).scalar() or 0
    open_bugs = (await db.execute(_w(select(func.count(WorkItem.id)).where(
        WorkItem.item_type == "BUG",
        WorkItem.status.notin_(["DONE", "SUPERSEDED", "REJECTED"])), WorkItem))).scalar() or 0
    retest_stmt = select(func.count(TestExecution.id)).join(
        TestRun, TestExecution.test_run_id == TestRun.id).where(
        TestExecution.status == "FAIL", TestExecution.bug_work_item_id.isnot(None))
    if eff:
        retest_stmt = retest_stmt.where(TestRun.project_id == eff)
    retest_pending = (await db.execute(retest_stmt)).scalar() or 0
    latest_run = (await db.execute(_w(select(TestRun).order_by(desc(TestRun.created_at)),
                                      TestRun))).scalars().first()
    # --- Phase 3: API stats ---
    from app.qa.api_models import APIEndpoint, APITestConfig
    ep_ids_stmt = select(APIEndpoint.id)
    if eff:
        ep_ids_stmt = ep_ids_stmt.where(APIEndpoint.project_id == eff)
    ep_ids = (await db.execute(ep_ids_stmt)).scalars().all()
    api_cfg_stmt = select(APITestConfig.test_case_id)
    if ep_ids:
        api_cfg_stmt = api_cfg_stmt.where(APITestConfig.endpoint_id.in_(ep_ids))
    else:
        api_cfg_stmt = api_cfg_stmt.where(False)
    api_case_ids = (await db.execute(api_cfg_stmt)).scalars().all()
    api_tests = len(api_case_ids)
    api_endpoints = len(ep_ids)
    api_endpoints_covered = 0
    if ep_ids:
        cov_rows = (await db.execute(select(APITestConfig.endpoint_id).where(
            APITestConfig.endpoint_id.in_(ep_ids)))).scalars().all()
        api_endpoints_covered = len(set(cov_rows))
    api_pass = api_fail = 0
    api_recent_failures: list = []
    if api_case_ids:
        api_pass = (await db.execute(select(func.count(TestExecution.id)).join(
            TestRun, TestExecution.test_run_id == TestRun.id).where(
            TestExecution.test_case_id.in_(api_case_ids),
            TestExecution.status == "PASS",
            *([TestRun.project_id == eff] if eff else [])))).scalar() or 0
        api_fail = (await db.execute(select(func.count(TestExecution.id)).join(
            TestRun, TestExecution.test_run_id == TestRun.id).where(
            TestExecution.test_case_id.in_(api_case_ids),
            TestExecution.status == "FAIL",
            *([TestRun.project_id == eff] if eff else [])))).scalar() or 0
        recent = (await db.execute(select(TestExecution).join(
            TestRun, TestExecution.test_run_id == TestRun.id).where(
            TestExecution.test_case_id.in_(api_case_ids),
            TestExecution.status == "FAIL",
            *([TestRun.project_id == eff] if eff else [])).order_by(
            desc(TestExecution.updated_at)).limit(5))).scalars().all()
        for r in recent:
            tc = (await db.execute(select(TestCase).where(TestCase.id == r.test_case_id))).scalars().first()
            api_recent_failures.append({"execution_id": r.id,
                                        "tc_code": tc.tc_code if tc else "",
                                        "title": tc.title if tc else ""})
    phase5 = await _phase5_overview_counts(db, eff)
    return {"project_id": project_id, "total_requirements": total_req,
            "reviewed_requirements": reviewed, "needs_clarification": blocked,
            "open_questions": open_q, "unapproved_ac": unapproved_ac,
            "covered_requirements": covered, "uncovered_requirements": uncovered,
            "testcase_draft": tc_draft, "testcase_approved": tc_approved,
            "active_runs": active_runs, "exec_pass": exec_pass, "exec_fail": exec_fail,
            "exec_blocked": exec_blocked, "exec_not_run": exec_not_run,
            "open_bugs": open_bugs, "retest_pending": retest_pending,
            "latest_build": latest_run.version_build if latest_run else None,
            "latest_build_status": latest_run.status if latest_run else None,
            "api_tests": api_tests, "api_pass": api_pass, "api_fail": api_fail,
            "api_endpoints": api_endpoints,
            "api_endpoints_covered": api_endpoints_covered,
            "api_recent_failures": api_recent_failures,
            **phase5}


# =========================================================================
# QUICK QA COPILOT (Human-Centric Studio)
# =========================================================================
class QuickQAAnalyzeRequest(BaseModel):
    project_id: Optional[str] = ""
    spec_text: str
    mode: str = "test_case_polish" # test_case_polish, bug_draft, dev_inquiry, spec_ambiguity, japan_test_data, quick_checklist
    custom_instruction: Optional[str] = ""
    is_auto_harvest: bool = False
    target_language: str = "bilingual"
    preferred_provider: str = "auto"
    model: Optional[str] = None

@router.post("/quick-analyze")
async def quick_qa_analyze(
    req: QuickQAAnalyzeRequest,
    db: AsyncSession = Depends(get_db)
):
    """Executes human-centric QA analysis across 6 real-world scenarios."""
    from app.qa.quick_qa_service import QuickQAService
    try:
        return await QuickQAService.analyze(req.model_dump(), db)
    except Exception as e:
        logger.error(f"Error in quick QA analyze: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

class QuickQASaveRequest(BaseModel):
    project_id: str
    item_type: str # test_case, bug, question
    title: str
    description: str
    steps: Optional[List[dict]] = None
    priority: str = "MEDIUM"

@router.post("/quick-save")
async def quick_qa_save(
    req: QuickQASaveRequest,
    db: AsyncSession = Depends(get_db)
):
    """Promotes quick QA findings into permanent QA Workspace entities."""
    try:
        if req.item_type == "test_case":
            tc_num = await E._next_tc_number(db, req.project_id)
            tc = TestCase(
                project_id=req.project_id,
                tc_code=f"TC-{tc_num:03d}",
                title=req.title[:255],
                case_type="Validation",
                priority=req.priority,
                purpose=req.description[:500],
                status="DRAFT",
                ai_generated=True
            )
            db.add(tc)
            await db.flush()
            if req.steps:
                for idx, st in enumerate(req.steps):
                    step = TestStep(
                        test_case_id=tc.id,
                        step_order=idx + 1,
                        action=st.get("action_ja") or st.get("action_vi") or str(st),
                        expected=st.get("expected_ja") or st.get("expected_vi") or ""
                    )
                    db.add(step)
            await db.commit()
            return {"status": "saved", "type": "test_case", "id": tc.id, "code": tc.tc_code}
        elif req.item_type == "bug":
            wi = WorkItem(
                project_id=req.project_id,
                item_type="BUG",
                title=req.title[:255],
                description=req.description,
                status="PROPOSED",
                priority=req.priority
            )
            db.add(wi)
            await db.commit()
            return {"status": "saved", "type": "bug", "id": wi.id}
        elif req.item_type == "question":
            q = QAOpenQuestion(
                project_id=req.project_id,
                question_vi=req.title,
                question_ja=req.description[:500],
                reason=req.description,
                status="DRAFT",
                ai_generated=True
            )
            db.add(q)
            await db.commit()
            return {"status": "saved", "type": "question", "id": q.id}
        else:
            raise HTTPException(status_code=400, detail="Unsupported item type")
    except Exception as e:
        logger.error(f"Error in quick QA save: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
