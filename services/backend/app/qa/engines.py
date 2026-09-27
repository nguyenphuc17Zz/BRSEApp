"""QA engines: review, questions, acceptance criteria, test cases, checklist, conflict check, coverage."""
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import logger
from app.intelligence.models import WorkItem, WorkItemEvidence, MeetingRecord
from app.qa.models import (
    QAFinding, QAOpenQuestion, AcceptanceCriterion, TestCase, TestStep, RequirementCoverage,
)
from app.qa.llm import generate_qa_json

VALID_FINDING_TYPES = {
    "Ambiguous", "MissingInformation", "MissingValidation", "MissingExpectedResult",
    "MissingErrorHandling", "MissingPermission", "MissingBoundary", "Conflict", "NonTestable",
}
VALID_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
VALID_KNOWLEDGE = {"Confirmed", "Inferred", "AISuggested"}
VALID_CASE_TYPES = {
    "Happy", "Negative", "Validation", "Boundary", "Permission",
    "DataIntegrity", "ErrorHandling", "StateTransition", "RegressionCandidate",
}


# ---------- helpers ----------
async def get_requirement(db: AsyncSession, requirement_id: str) -> Optional[WorkItem]:
    stmt = (
        select(WorkItem)
        .options(selectinload(WorkItem.evidence_items))
        .where(WorkItem.id == requirement_id)
    )
    res = await db.execute(stmt)
    return res.scalars().first()


async def ensure_req_code(db: AsyncSession, item: WorkItem) -> str:
    if item.req_code:
        return item.req_code
    res = await db.execute(
        select(WorkItem.req_code).where(
            WorkItem.project_id == item.project_id,
            WorkItem.item_type == "REQUIREMENT",
            WorkItem.req_code.isnot(None),
        )
    )
    max_n = 0
    for (code,) in res.all():
        m = re.search(r"(\d+)$", code or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    item.req_code = f"REQ-{max_n + 1:03d}"
    await db.flush()
    return item.req_code


async def load_project_context(db: AsyncSession, project_id: str) -> Tuple[List[WorkItem], List[WorkItem], str]:
    """Returns (decisions, sibling_requirements, rag_context)."""
    dec_res = await db.execute(
        select(WorkItem).where(
            WorkItem.project_id == project_id,
            WorkItem.item_type == "DECISION",
            WorkItem.status == "CONFIRMED",
        ).order_by(WorkItem.created_at.desc()).limit(20)
    )
    decisions = list(dec_res.scalars().all())
    req_res = await db.execute(
        select(WorkItem).where(
            WorkItem.project_id == project_id,
            WorkItem.item_type == "REQUIREMENT",
        ).order_by(WorkItem.created_at.desc()).limit(30)
    )
    siblings = list(req_res.scalars().all())
    rag_context = ""
    try:
        from app.intelligence.rag.project_rag_service import project_rag_service
        rag = await project_rag_service.build_rag_context(db, project_id, "", max_tokens=1200)
        if isinstance(rag, dict):
            rag_context = rag.get("context_markdown", "") or ""
        elif isinstance(rag, str):
            rag_context = rag
    except Exception as e:
        logger.warning(f"QA RAG context unavailable: {e}")
    return decisions, siblings, rag_context[:3000]


def _clean(v: Any, default: str = "") -> str:
    return str(v).strip() if v is not None else default


def _norm_enum(v: Any, valid: set, default: str) -> str:
    s = _clean(v)
    return s if s in valid else default


# ---------- Review ----------
REVIEW_SYSTEM = (
    "You are a senior QA analyst and BrSE. Review the requirement strictly from the provided evidence. "
    "NEVER invent business rules. If evidence is insufficient, conclude 'Not enough information' "
    "as a MissingInformation finding. Mark best-practice suggestions as knowledge_class='AISuggested'."
)

REVIEW_CHECKS = """- Is the requirement clear and unambiguous?
- Missing preconditions / triggers?
- Missing input validations?
- Missing expected result?
- Missing error handling (failure behavior)?
- Missing permission / role checks?
- Missing boundary conditions (empty, max, format, encoding)?
- Are state transitions clear?
- Inconsistent terminology?
- Conflict with existing decisions / requirements / meeting history?
- Is the requirement testable at all?"""


async def review_requirement(
    db: AsyncSession,
    requirement_id: str,
    preferred_provider: Optional[str] = None,
    model: Optional[str] = None,
    force: bool = False,
) -> List[QAFinding]:
    item = await get_requirement(db, requirement_id)
    if not item:
        raise ValueError("Requirement not found")
    await ensure_req_code(db, item)

    if not force:
        existing = (await db.execute(
            select(QAFinding).where(QAFinding.requirement_id == requirement_id)
        )).scalars().all()
        if existing:
            return existing

    decisions, siblings, rag_context = await load_project_context(db, item.project_id)
    evidence_lines = [f"- [{e.source_type}] {e.quote_text}" for e in (item.evidence_items or [])]
    if not evidence_lines:
        evidence_lines = ["- (No linked evidence; requirement text itself is the source)"]
    decision_lines = [f"- {d.title}: {d.description[:200]}" for d in decisions] or ["- (none)"]
    sibling_lines = [
        f"- {(s.req_code or s.id[:6])}: {s.title}" for s in siblings if s.id != item.id
    ] or ["- (none)"]

    prompt = f"""Review the following software requirement and report QA findings.

Requirement [{item.req_code or item.id[:6]}]: {item.title}
Description: {item.description}
Details: {item.details_json}

Evidence (original sources):
{chr(10).join(evidence_lines)}

Confirmed project decisions (check conflicts):
{chr(10).join(decision_lines)}

Other project requirements (check terminology / conflicts):
{chr(10).join(sibling_lines)}

Project document context:
{rag_context or '(none)'}

Checks to perform:
{REVIEW_CHECKS}

Return strict JSON:
{{
  "findings": [
    {{
      "title": "Short finding title",
      "description": "What is unclear or missing and why it matters",
      "finding_type": "Ambiguous | MissingInformation | MissingValidation | MissingExpectedResult | MissingErrorHandling | MissingPermission | MissingBoundary | Conflict | NonTestable",
      "severity": "CRITICAL | HIGH | MEDIUM | LOW",
      "confidence": 0.85,
      "evidence_quote": "Exact quote from requirement or evidence supporting this finding",
      "knowledge_class": "Confirmed | Inferred | AISuggested",
      "suggested_action": "Concrete next step (e.g. ask client, add validation)"
    }}
  ]
}}
Rules: every finding MUST include evidence_quote (use the requirement sentence itself if nothing else).
Use knowledge_class='Confirmed' only when directly supported by evidence; 'Inferred' for reasonable deduction; 'AISuggested' for QA best-practice proposals.
If the requirement is fully clear, return {{"findings": []}}."""

    parsed = await generate_qa_json(prompt, REVIEW_SYSTEM, preferred_provider, model, max_tokens=2000)
    raw_findings = parsed.get("findings", []) if isinstance(parsed, dict) else []

    findings: List[QAFinding] = []
    for f in raw_findings:
        if not isinstance(f, dict):
            continue
        findings.append(QAFinding(
            project_id=item.project_id,
            requirement_id=item.id,
            title=_clean(f.get("title"))[:255] or "QA Finding",
            description=_clean(f.get("description")),
            finding_type=_norm_enum(f.get("finding_type"), VALID_FINDING_TYPES, "Ambiguous"),
            severity=_norm_enum(f.get("severity"), VALID_SEVERITIES, "MEDIUM"),
            confidence=float(f.get("confidence", 0.8) or 0.8),
            evidence_quote=_clean(f.get("evidence_quote")) or item.title,
            evidence_source_type="requirement",
            evidence_source_id=item.id,
            knowledge_class=_norm_enum(f.get("knowledge_class"), VALID_KNOWLEDGE, "Inferred"),
            suggested_action=_clean(f.get("suggested_action")) or None,
            status="OPEN",
            ai_generated=True,
        ))

    if not findings and not parsed:
        findings = _heuristic_review_fallback(item)

    for f in findings:
        db.add(f)
    await db.flush()
    await refresh_coverage(db, item.id)
    await db.commit()
    for f in findings:
        await db.refresh(f)
    return findings


def _heuristic_review_fallback(item: WorkItem) -> List[QAFinding]:
    """Offline safety net: deterministic checks, always marked AISuggested with modest confidence."""
    text = f"{item.title}\n{item.description}".lower()
    out: List[QAFinding] = []
    src = f"{item.title} {item.description}".strip()[:500] or item.title

    def add(title, desc, ftype, sev, action):
        out.append(QAFinding(
            project_id=item.project_id, requirement_id=item.id, title=title,
            description=desc, finding_type=ftype, severity=sev, confidence=0.6,
            evidence_quote=src, evidence_source_type="requirement", evidence_source_id=item.id,
            knowledge_class="AISuggested", suggested_action=action, status="OPEN", ai_generated=True,
        ))

    if len(text.strip()) < 20:
        add("Not enough information: requirement too brief",
            "Requirement text is too short to derive behavior, validations, or expected results.",
            "MissingInformation", "HIGH", "Ask the client for detailed specification.")
        return out
    error_kw = ["lỗi", "error", "失敗", "エラー", "exception", "thất bại", "không thành công"]
    if not any(k in text for k in error_kw):
        add("Missing error handling behavior",
            "No behavior described when the operation fails (error message, rollback, retry).",
            "MissingErrorHandling", "MEDIUM",
            "Confirm failure behavior with the client before writing test cases.")
    if not any(k in text for k in ["quyền", "permission", "権限", "role", "vai trò", "admin", "user"]):
        add("Missing permission / role clarification",
            "Requirement does not state which roles are allowed to perform this action.",
            "MissingPermission", "LOW",
            "Confirm target user roles with the client.")
    boundary_kw = ["tối đa", "tối thiểu", "上限", "下限", "boundary", "null", "empty", "空", "định dạng", "format"]
    if not any(k in text for k in boundary_kw):
        add("Missing boundary conditions",
            "No boundary values stated (empty, max length, format, encoding).",
            "MissingBoundary", "LOW",
            "Ask about limits, formats, and edge values.")
    return out


# ---------- Open Questions ----------
QUESTION_SYSTEM = (
    "You are a senior BrSE writing confirmation questions to a Japanese client. "
    "Questions in Japanese must use polite confirmation keigo (ご確認いただけますでしょうか). "
    "Always include why it matters (reason) and the risk if left unanswered."
)


async def generate_questions(
    db: AsyncSession,
    requirement_id: str,
    finding_ids: Optional[List[str]] = None,
    preferred_provider: Optional[str] = None,
    model: Optional[str] = None,
) -> List[QAOpenQuestion]:
    item = await get_requirement(db, requirement_id)
    if not item:
        raise ValueError("Requirement not found")
    stmt = select(QAFinding).where(
        QAFinding.requirement_id == requirement_id,
        QAFinding.status == "OPEN",
    )
    if finding_ids:
        stmt = stmt.where(QAFinding.id.in_(finding_ids))
    findings = (await db.execute(stmt)).scalars().all()
    if not findings:
        return []

    finding_lines = "\n".join(
        f"- [{f.id}] {f.title} ({f.finding_type} / {f.severity}): {f.description} | Evidence: {f.evidence_quote}"
        for f in findings
    )
    prompt = f"""From these QA findings, write one client confirmation question per finding.

Requirement [{item.req_code or ''}]: {item.title}
Description: {item.description}

Findings:
{finding_lines}

Return strict JSON:
{{
  "questions": [
    {{
      "finding_id": "<finding id from the list>",
      "question_vi": "Câu hỏi xác nhận bằng tiếng Việt (rõ ràng, lịch sự)",
      "question_ja": "確認質問を丁寧な敬語で（ご確認いただけますでしょうか）",
      "reason": "Why this must be confirmed",
      "evidence_quote": "Quote supporting the question",
      "risk_if_unanswered": "What can go wrong if unanswered"
    }}
  ]
}}"""
    parsed = await generate_qa_json(prompt, QUESTION_SYSTEM, preferred_provider, model, max_tokens=2000)
    raw = parsed.get("questions", []) if isinstance(parsed, dict) else []
    by_id = {f.id: f for f in findings}

    questions: List[QAOpenQuestion] = []
    for q in raw:
        if not isinstance(q, dict):
            continue
        f = by_id.get(_clean(q.get("finding_id")), None)
        questions.append(QAOpenQuestion(
            project_id=item.project_id, requirement_id=item.id,
            finding_id=f.id if f else None,
            question_vi=_clean(q.get("question_vi")) or _clean(q.get("question_ja")),
            question_ja=_clean(q.get("question_ja")),
            reason=_clean(q.get("reason")),
            evidence_quote=_clean(q.get("evidence_quote")) or (f.evidence_quote if f else item.title),
            risk_if_unanswered=_clean(q.get("risk_if_unanswered")) or None,
            status="DRAFT", ai_generated=True,
        ))
    if not questions and not parsed:
        for f in findings:
            questions.append(QAOpenQuestion(
                project_id=item.project_id, requirement_id=item.id, finding_id=f.id,
                question_vi=f"Vui lòng xác nhận: {f.title} — {f.description}"[:500],
                question_ja=f"「{f.title}」についてご確認いただけますでしょうか。",
                reason=f.description or f.title,
                evidence_quote=f.evidence_quote or item.title,
                risk_if_unanswered="Hiểu sai yêu cầu dẫn đến implement và test sai.",
                status="DRAFT", ai_generated=True,
            ))
    for q in questions:
        db.add(q)
    await db.flush()
    await refresh_coverage(db, item.id)
    await db.commit()
    for q in questions:
        await db.refresh(q)
    return questions


# ---------- Acceptance Criteria ----------
AC_SYSTEM = (
    "You are a senior BA writing Given/When/Then acceptance criteria strictly from the requirement evidence. "
    "Do not invent business rules; mark deduced criteria as Inferred."
)


async def generate_acceptance_criteria(
    db: AsyncSession,
    requirement_id: str,
    preferred_provider: Optional[str] = None,
    model: Optional[str] = None,
) -> List[AcceptanceCriterion]:
    item = await get_requirement(db, requirement_id)
    if not item:
        raise ValueError("Requirement not found")
    existing = (await db.execute(
        select(func.count(AcceptanceCriterion.id)).where(AcceptanceCriterion.requirement_id == requirement_id)
    )).scalar() or 0

    evidence = "; ".join(e.quote_text for e in (item.evidence_items or [])[:4]) or item.title
    prompt = f"""Write acceptance criteria in Given/When/Then format for this requirement.

Requirement [{item.req_code or ''}]: {item.title}
Description: {item.description}
Evidence: {evidence}

Return strict JSON:
{{
  "criteria": [
    {{"given": "...", "when": "...", "then": "...", "knowledge_class": "Confirmed | Inferred | AISuggested", "evidence_quote": "..."}}
  ]
}}
Cover happy path first, then the most valuable negative/edge variants. Keep the set small (2-5 items)."""
    parsed = await generate_qa_json(prompt, AC_SYSTEM, preferred_provider, model, max_tokens=1500)
    raw = parsed.get("criteria", []) if isinstance(parsed, dict) else []

    criteria: List[AcceptanceCriterion] = []
    idx = existing
    for c in raw:
        if not isinstance(c, dict):
            continue
        idx += 1
        criteria.append(AcceptanceCriterion(
            project_id=item.project_id, requirement_id=item.id, ac_code=f"AC-{idx:03d}",
            given_text=_clean(c.get("given")), when_text=_clean(c.get("when")), then_text=_clean(c.get("then")),
            knowledge_class=_norm_enum(c.get("knowledge_class"), VALID_KNOWLEDGE, "Confirmed"),
            evidence_quote=_clean(c.get("evidence_quote")) or item.title,
            status="DRAFT", ai_generated=True,
        ))
    if not criteria:
        idx += 1
        criteria.append(AcceptanceCriterion(
            project_id=item.project_id, requirement_id=item.id, ac_code=f"AC-{idx:03d}",
            given_text="User is on the target screen with valid preconditions.",
            when_text=f"User performs the action: {item.title}",
            then_text="System behaves as described in the requirement.",
            knowledge_class="Inferred", evidence_quote=item.title, status="DRAFT", ai_generated=True,
        ))
    for c in criteria:
        db.add(c)
    await db.flush()
    await refresh_coverage(db, item.id)
    await db.commit()
    for c in criteria:
        await db.refresh(c)
    return criteria


# ---------- Test Cases ----------
TC_SYSTEM = (
    "You are a senior QA engineer. Generate a small set of high-value test cases (no duplicates). "
    "Only include case types that fit the requirement. Every case needs structured steps with action + expected."
)


async def _next_tc_number(db: AsyncSession, project_id: str) -> int:
    res = await db.execute(select(TestCase.tc_code).where(TestCase.project_id == project_id))
    max_n = 0
    for (code,) in res.all():
        m = re.search(r"(\d+)$", code or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n + 1


async def generate_test_cases(
    db: AsyncSession,
    requirement_id: str,
    acceptance_criterion_ids: Optional[List[str]] = None,
    checklist_mode: bool = False,
    preferred_provider: Optional[str] = None,
    model: Optional[str] = None,
) -> List[TestCase]:
    item = await get_requirement(db, requirement_id)
    if not item:
        raise ValueError("Requirement not found")
    ac_stmt = select(AcceptanceCriterion).where(AcceptanceCriterion.requirement_id == requirement_id)
    if acceptance_criterion_ids:
        ac_stmt = ac_stmt.where(AcceptanceCriterion.id.in_(acceptance_criterion_ids))
    ac_list = (await db.execute(ac_stmt)).scalars().all()
    decisions, _, _ = await load_project_context(db, item.project_id)

    ac_block = "\n".join(
        f"- [{a.ac_code}] Given {a.given_text} When {a.when_text} Then {a.then_text}" for a in ac_list
    ) or "(No acceptance criteria yet — derive from requirement text)"
    decision_block = "\n".join(f"- {d.title}: {d.description[:200]}" for d in decisions[:10]) or "(none)"
    mode_hint = (
        "QUICK CHECKLIST MODE: produce 4-8 single-step checklist items for a small change "
        "(export, wording, config, simple validation). Use case_type 'Validation' and purpose starting with '[Quick Checklist]'."
        if checklist_mode else
        "FULL MODE: produce 3-7 test cases covering only fitting types among "
        "Happy, Negative, Validation, Boundary, Permission, DataIntegrity, ErrorHandling, StateTransition, RegressionCandidate."
    )

    prompt = f"""{mode_hint}

Requirement [{item.req_code or ''}]: {item.title}
Description: {item.description}

Acceptance criteria:
{ac_block}

Related confirmed decisions:
{decision_block}

Return strict JSON:
{{
  "cases": [
    {{
      "title": "Short test title",
      "purpose": "Why this case matters",
      "case_type": "Happy | Negative | Validation | Boundary | Permission | DataIntegrity | ErrorHandling | StateTransition | RegressionCandidate",
      "priority": "CRITICAL | HIGH | MEDIUM | LOW",
      "preconditions": "...",
      "expected_result": "...",
      "acceptance_criterion_code": "AC-001 or empty",
      "knowledge_class": "Confirmed | Inferred | AISuggested",
      "evidence_quote": "...",
      "confidence": 0.85,
      "steps": [{{"action": "...", "expected": "..."}}]
    }}
  ]
}}
Avoid near-duplicate cases; merge overlapping ones. Mark best-practice extras as AISuggested."""
    parsed = await generate_qa_json(prompt, TC_SYSTEM, preferred_provider, model, max_tokens=2500)
    raw = parsed.get("cases", []) if isinstance(parsed, dict) else []
    ac_by_code = {a.ac_code: a.id for a in ac_list}

    start_n = await _next_tc_number(db, item.project_id)
    cases: List[TestCase] = []
    seen_titles = set()
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            continue
        title = _clean(c.get("title"))[:255] or f"Test case {i + 1}"
        key = re.sub(r"\W+", "", title.lower())
        if key in seen_titles:
            continue
        seen_titles.add(key)
        ac_code = _clean(c.get("acceptance_criterion_code"))
        steps_in = c.get("steps") if isinstance(c.get("steps"), list) else []
        tc = TestCase(
            project_id=item.project_id, tc_code=f"TC-{start_n + len(cases):03d}",
            title=title, purpose=_clean(c.get("purpose")),
            case_type=_norm_enum(c.get("case_type"), VALID_CASE_TYPES, "Validation" if checklist_mode else "Happy"),
            priority=_clean(c.get("priority")).upper() or "MEDIUM",
            preconditions=_clean(c.get("preconditions")),
            expected_result=_clean(c.get("expected_result")),
            requirement_id=item.id,
            acceptance_criterion_id=ac_by_code.get(ac_code),
            evidence_quote=_clean(c.get("evidence_quote")) or item.title,
            knowledge_class=_norm_enum(c.get("knowledge_class"), VALID_KNOWLEDGE, "Confirmed"),
            source="AI", ai_generated=True,
            confidence=float(c.get("confidence", 0.8) or 0.8),
            status="DRAFT",
        )
        db.add(tc)
        await db.flush()
        order = 0
        for s in steps_in:
            if not isinstance(s, dict):
                continue
            order += 1
            db.add(TestStep(test_case_id=tc.id, step_order=order,
                            action=_clean(s.get("action")) or "...",
                            expected=_clean(s.get("expected"))))
        if order == 0:
            db.add(TestStep(test_case_id=tc.id, step_order=1,
                            action=f"Execute: {title}",
                            expected=tc.expected_result or "Expected behavior observed."))
        cases.append(tc)
    if not cases:
        tc = TestCase(
            project_id=item.project_id, tc_code=f"TC-{start_n:03d}",
            title=f"Happy path: {item.title[:120]}", purpose="Verify the main behavior works.",
            case_type="Happy", priority="HIGH",
            preconditions="Valid preconditions are met.",
            expected_result="System behaves as required.",
            requirement_id=item.id,
            acceptance_criterion_id=ac_list[0].id if ac_list else None,
            evidence_quote=item.title, knowledge_class="Inferred",
            source="AI", ai_generated=True, confidence=0.6, status="DRAFT",
        )
        db.add(tc)
        await db.flush()
        db.add(TestStep(test_case_id=tc.id, step_order=1,
                        action=f"Perform: {item.title}",
                        expected="System behaves as required."))
        cases.append(tc)
    await refresh_coverage(db, item.id)
    await db.commit()
    for tc in cases:
        await db.refresh(tc)
    return cases


# ---------- Coverage ----------
def compute_coverage_status(
    has_review: bool, findings_open: int, questions_unanswered: int,
    ac_total: int, ac_approved: int, tc_total: int,
) -> str:
    if not has_review:
        return "NotReviewed"
    if findings_open > 0 or questions_unanswered > 0:
        return "BlockedByClarification"
    if tc_total == 0:
        return "NotCovered"
    if ac_total > 0 and ac_approved < ac_total:
        return "PartiallyCovered"
    return "Covered"


async def refresh_coverage(db: AsyncSession, requirement_id: str) -> RequirementCoverage:
    item = await get_requirement(db, requirement_id)
    if not item:
        raise ValueError("Requirement not found")
    has_review = (await db.execute(
        select(func.count(QAFinding.id)).where(QAFinding.requirement_id == requirement_id)
    )).scalar() or 0
    findings_open = (await db.execute(
        select(func.count(QAFinding.id)).where(
            QAFinding.requirement_id == requirement_id, QAFinding.status == "OPEN")
    )).scalar() or 0
    questions_unanswered = (await db.execute(
        select(func.count(QAOpenQuestion.id)).where(
            QAOpenQuestion.requirement_id == requirement_id,
            QAOpenQuestion.status.in_(["DRAFT", "APPROVED"]))
    )).scalar() or 0
    ac_total = (await db.execute(
        select(func.count(AcceptanceCriterion.id)).where(AcceptanceCriterion.requirement_id == requirement_id)
    )).scalar() or 0
    ac_approved = (await db.execute(
        select(func.count(AcceptanceCriterion.id)).where(
            AcceptanceCriterion.requirement_id == requirement_id, AcceptanceCriterion.status == "APPROVED")
    )).scalar() or 0
    tc_total = (await db.execute(
        select(func.count(TestCase.id)).where(TestCase.requirement_id == requirement_id)
    )).scalar() or 0
    tc_approved = (await db.execute(
        select(func.count(TestCase.id)).where(
            TestCase.requirement_id == requirement_id, TestCase.status == "APPROVED")
    )).scalar() or 0
    status = compute_coverage_status(bool(has_review), findings_open, questions_unanswered, ac_total, ac_approved, tc_total)
    cov = (await db.execute(
        select(RequirementCoverage).where(RequirementCoverage.requirement_id == requirement_id)
    )).scalars().first()
    if not cov:
        cov = RequirementCoverage(project_id=item.project_id, requirement_id=requirement_id)
        db.add(cov)
    cov.has_review = bool(has_review)
    cov.findings_open = findings_open
    cov.questions_unanswered = questions_unanswered
    cov.ac_total = ac_total
    cov.ac_approved = ac_approved
    cov.tc_total = tc_total
    cov.tc_approved = tc_approved
    cov.status = status
    await db.flush()
    return cov
