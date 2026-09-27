"""UI failure analysis: preliminary buckets (never root-cause claims), flaky
detection, and automation candidacy recommendations."""
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.qa.models import TestCase
from app.qa.execution_models import TestExecution, TestEvidence
from app.qa.api_testing import redact as R
from app.qa.llm import generate_qa_json

ANALYZE_SYSTEM = (
    "You are a QA analyst triaging a Playwright UI test failure. "
    "Classify into exactly one preliminary bucket. NEVER state a root cause as fact. "
    "Use hedging language: Possible / Likely based on evidence."
)

BUCKETS = {"Possible Application Bug", "Possible Automation Script Issue",
           "Possible Selector Issue", "Possible Test Data Issue",
           "Possible Environment Issue", "Timeout", "Unknown"}


async def analyze_ui_failure(
    db: AsyncSession, execution_id: str, preferred_provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    ex = (await db.execute(select(TestExecution).where(TestExecution.id == execution_id))).scalars().first()
    if not ex:
        raise ValueError("Execution not found")
    tc = (await db.execute(select(TestCase).where(TestCase.id == ex.test_case_id))).scalars().first()
    ev_rows = (await db.execute(select(TestEvidence).where(
        TestEvidence.execution_id == ex.id))).scalars().all()
    tech = next((e.text_content or "" for e in ev_rows if e.evidence_type == "console_error"), "")
    shots = [e.file_path for e in ev_rows if e.evidence_type == "screenshot"]
    try:
        actual = json.loads(ex.actual_result or "{}")
    except Exception:
        actual = {}
    clean_ctx, _ = R.redact_for_ai({
        "test": f"{tc.tc_code if tc else ''} {tc.title if tc else ''}",
        "failed_step": actual.get("failed_step", {}),
        "failed_assertion": actual.get("failed_assertion", ""),
        "current_url": actual.get("current_url", ""),
        "error_class": actual.get("error_class", ""),
        "console_and_network": (tech or "")[:1500],
        "screenshots": len(shots),
    })
    prompt = f"""Triage this UI automation failure. Facts only.

Context: {json.dumps(clean_ctx, ensure_ascii=False, default=str)[:3000]}

Return strict JSON:
{{"bucket": "<one of: Possible Application Bug | Possible Automation Script Issue | Possible Selector Issue | Possible Test Data Issue | Possible Environment Issue | Timeout | Unknown>",
  "reasoning": "2-3 sentences with Possible/Likely hedging, e.g. backend 500 suggests application side",
  "suggested_next_steps": ["..."]}}"""
    parsed = await generate_qa_json(prompt, ANALYZE_SYSTEM, preferred_provider, model, max_tokens=800)
    bucket = (parsed.get("bucket") if isinstance(parsed, dict) else None) or "Unknown"
    if bucket not in BUCKETS:
        bucket = "Unknown"
    return {"bucket": bucket,
            "reasoning": (parsed.get("reasoning") if isinstance(parsed, dict) else "") or "",
            "suggested_next_steps": (parsed.get("suggested_next_steps") if isinstance(parsed, dict) else []) or [],
            "failed_step": actual.get("failed_step", {}),
            "screenshots": shots}


async def detect_flaky(db: AsyncSession, test_case_id: str, window: int = 6) -> Dict[str, Any]:
    """Flags Potentially Flaky on alternating PASS/FAIL under same conditions."""
    rows = (await db.execute(select(TestExecution).where(
        TestExecution.test_case_id == test_case_id,
        TestExecution.status.in_(["PASS", "FAIL"])).order_by(
        desc(TestExecution.updated_at)).limit(window))).scalars().all()
    seq = [r.status for r in rows]
    alternations = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
    flaky = len(seq) >= 4 and alternations >= 3
    return {"sequence": seq, "alternations": alternations,
            "flaky": flaky,
            "label": "Potentially Flaky" if flaky else "Stable"}


async def recommend_candidates(db: AsyncSession, project_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Recommends automation candidates: approved manual cases already runnable, stable, high value."""
    from app.qa.ui_models import UIAutomationScript
    cases = (await db.execute(select(TestCase).where(
        TestCase.project_id == project_id,
        TestCase.status == "APPROVED").order_by(desc(TestCase.updated_at)).limit(100)
    )).scalars().all()
    scripted = set((await db.execute(select(UIAutomationScript.test_case_id))).scalars().all())
    out = []
    for tc in cases:
        if tc.id in scripted:
            continue
        score = 0
        reasons = []
        if (tc.priority or "").upper() in ("HIGH", "CRITICAL"):
            score += 2
            reasons.append("high business value")
        if "regression" in (tc.purpose or "").lower() or "smoke" in (tc.title or "").lower():
            score += 2
            reasons.append("regression/smoke")
        if tc.expected_result and len(tc.expected_result) > 10:
            score += 1
            reasons.append("deterministic expected result")
        hist = (await db.execute(select(TestExecution.status).where(
            TestExecution.test_case_id == tc.id,
            TestExecution.status.in_(["PASS", "FAIL"])).order_by(
            desc(TestExecution.updated_at)).limit(4))).scalars().all()
        if len(hist) >= 2:
            score += 1
            reasons.append("run repeatedly")
        if score >= 2:
            out.append({"test_case_id": tc.id, "tc_code": tc.tc_code,
                        "title": tc.title, "score": score, "reasons": reasons})
    out.sort(key=lambda x: -x["score"])
    return out[:limit]
