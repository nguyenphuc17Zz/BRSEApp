"""AI scenario design + assertion suggestion + FAIL analysis for API tests.

Secrets are redacted before any AI call. AI outputs are always DRAFT and the
analyzer never concludes a root cause (4 preliminary buckets only).
"""
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.qa.models import TestCase, TestStep
from app.qa.api_models import APIEndpoint, APITestConfig, APIAssertion
from app.qa import engines as E1
from app.qa.llm import generate_qa_json
from app.qa.api_testing import redact as R

API_SYSTEM = (
    "You are a senior QA automation engineer designing API tests. "
    "Propose only test categories that fit THIS endpoint. "
    "Mark knowledge_class='Confirmed' when the spec states the rule, "
    "else 'AISuggested' for best-practice extras. Never invent business rules."
)

CATEGORY_HINTS = """Valid Request, Missing Required Field, Invalid Value, Invalid Data Type,
Boundary, Empty Value, Null, Authentication, Authorization, Duplicate,
Invalid State, Not Found, Conflict, Business Validation, Response Schema, Error Handling"""


async def generate_api_tests(
    db: AsyncSession, endpoint_id: str, requirement_id: Optional[str] = None,
    max_cases: int = 8, preferred_provider: Optional[str] = None,
    model: Optional[str] = None,
) -> List[TestCase]:
    ep = (await db.execute(select(APIEndpoint).where(APIEndpoint.id == endpoint_id))).scalars().first()
    if not ep:
        raise ValueError("Endpoint not found")
    req = await E1.get_requirement(db, requirement_id or ep.requirement_id) if (requirement_id or ep.requirement_id) else None
    project_id = ep.project_id

    def _j(t: str, d: Any) -> str:
        try:
            return json.dumps(json.loads(t or "") if (t or "").strip() else (d or {}),
                              ensure_ascii=False, default=str)[:2500]
        except Exception:
            return str(t or "")[:2500]

    prompt = f"""Design API test cases for this endpoint. Keep the set small ({max_cases} max), no near-duplicates.

Endpoint: {ep.method} {ep.path} (auth: {ep.auth_type})
Description: {ep.description or ep.name}
Parameters: {_j(ep.parameters_json, [])}
Request body schema: {_j(ep.request_body_json, {})}
Responses: {_j(ep.responses_json, {})}
Requirement: {(req.title if req else '')} — {(req.description if req else '')[:800]}

Candidate categories (use only fitting ones):
{CATEGORY_HINTS}

Return strict JSON:
{{
  "cases": [
    {{
      "title": "Short test title",
      "purpose": "Why this case matters",
      "category": "<one of the categories above>",
      "priority": "CRITICAL | HIGH | MEDIUM | LOW",
      "knowledge_class": "Confirmed | AISuggested",
      "evidence_quote": "Spec/requirement sentence supporting this case",
      "method": "{ep.method}", "path_params": {{}}, "query": {{}}, "body": {{}},
      "expected_status": 200,
      "assertions": [{{"field": "status|json|header|time|empty", "target": "data.id", "operator": "eq|exists|...", "expected": "..."}}]
    }}
  ]
}}"""
    parsed = await generate_qa_json(prompt, API_SYSTEM, preferred_provider, model, max_tokens=2500)
    raw = parsed.get("cases", []) if isinstance(parsed, dict) else []

    created: List[TestCase] = []
    start_n = await E1._next_tc_number(db, project_id)
    for i, c in enumerate(raw[:max_cases]):
        if not isinstance(c, dict):
            continue
        title = str(c.get("title") or f"API test {i + 1}")[:255]
        kc = c.get("knowledge_class") if c.get("knowledge_class") in ("Confirmed", "Inferred", "AISuggested") else "AISuggested"
        tc = TestCase(
            project_id=project_id, tc_code=f"TC-{start_n + len(created):03d}",
            title=title, purpose=str(c.get("purpose") or ""),
            case_type=str(c.get("category") or "Validation")[:30],
            priority=str(c.get("priority") or "MEDIUM").upper(),
            preconditions=f"Environment ready. Endpoint {ep.method} {ep.path}.",
            expected_result=f"Status {c.get('expected_status', 200)} and assertions hold.",
            requirement_id=req.id if req else (ep.requirement_id or ""),
            evidence_quote=str(c.get("evidence_quote") or f"{ep.method} {ep.path} spec"),
            knowledge_class=kc, source="AI", ai_generated=True,
            confidence=0.8, status="DRAFT")
        if not tc.requirement_id:
            # API test without a requirement link: attach to endpoint only via config
            raise ValueError("API tests require a linked requirement (link endpoint to a requirement first).")
        db.add(tc)
        await db.flush()
        body = c.get("body")
        cfg = APITestConfig(
            test_case_id=tc.id, endpoint_id=ep.id, method=str(c.get("method") or ep.method).upper(),
            url_template="{{BASE_URL}}" + ep.path,
            query_json=json.dumps(c.get("query") or {}, ensure_ascii=False),
            path_params_json=json.dumps(c.get("path_params") or {}, ensure_ascii=False),
            body_text=json.dumps(body, ensure_ascii=False) if isinstance(body, (dict, list)) else str(body or ""),
            expected_status=int(c.get("expected_status") or 200),
            spec_version=ep.spec_version)
        db.add(cfg)
        await db.flush()
        db.add(TestStep(test_case_id=tc.id, step_order=1,
                        action=f"Send {cfg.method} {ep.path}",
                        expected=f"Status {cfg.expected_status}, assertions hold."))
        for a in (c.get("assertions") or []):
            if not isinstance(a, dict):
                continue
            db.add(APIAssertion(test_case_id=tc.id, field=str(a.get("field") or "status")[:20],
                                target=str(a.get("target") or "")[:500],
                                operator=str(a.get("operator") or "eq")[:20],
                                expected_value=None if a.get("expected") is None else str(a.get("expected")),
                                status="DRAFT", ai_generated=True))
        created.append(tc)
    await db.commit()
    for tc in created:
        await db.refresh(tc)
    return created


async def suggest_assertions(
    db: AsyncSession, test_case_id: str, sample_response: Optional[Dict[str, Any]] = None,
    preferred_provider: Optional[str] = None, model: Optional[str] = None,
) -> List[APIAssertion]:
    """AI proposes assertions (DRAFT) from spec + optional sample response (redacted)."""
    cfg = (await db.execute(select(APITestConfig).where(
        APITestConfig.test_case_id == test_case_id))).scalars().first()
    if not cfg:
        raise ValueError("No API config for this test case.")
    clean_sample, _ = R.redact_for_ai(sample_response or {})
    prompt = f"""Propose response assertions for this API test. Return strict JSON:
{{"assertions": [{{"field": "status|json|header|time|empty", "target": "data.id", "operator": "eq", "expected": "..."}}]}}

Endpoint: {cfg.method} {cfg.url_template}, expected status {cfg.expected_status}
Sample response (secrets already redacted):
{json.dumps(clean_sample, ensure_ascii=False, default=str)[:2500]}"""
    parsed = await generate_qa_json(
        prompt, "You are a QA automation engineer writing response assertions. Output valid JSON only.",
        preferred_provider, model, max_tokens=1200)
    raw = parsed.get("assertions", []) if isinstance(parsed, dict) else []
    out: List[APIAssertion] = []
    for a in raw[:12]:
        if not isinstance(a, dict):
            continue
        row = APIAssertion(test_case_id=test_case_id, field=str(a.get("field") or "status")[:20],
                           target=str(a.get("target") or "")[:500],
                           operator=str(a.get("operator") or "eq")[:20],
                           expected_value=None if a.get("expected") is None else str(a.get("expected")),
                           status="DRAFT", ai_generated=True)
        db.add(row)
        out.append(row)
    await db.commit()
    for r in out:
        await db.refresh(r)
    return out


ANALYZE_SYSTEM = (
    "You are a QA analyst triaging an API test failure. Classify only. "
    "NEVER state a root cause as fact."
)


async def analyze_failure(
    db: AsyncSession, execution_id: str, preferred_provider: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Compares expected vs actual evidence and returns a preliminary bucket + diff highlights."""
    from app.qa.execution_models import TestExecution, TestEvidence
    ex = (await db.execute(select(TestExecution).where(TestExecution.id == execution_id))).scalars().first()
    if not ex:
        raise ValueError("Execution not found")
    tc = (await db.execute(select(TestCase).where(TestCase.id == ex.test_case_id))).scalars().first()
    cfg = (await db.execute(select(APITestConfig).where(
        APITestConfig.test_case_id == ex.test_case_id))).scalars().first()
    ev_rows = (await db.execute(select(TestEvidence).where(
        TestEvidence.execution_id == ex.id))).scalars().all()
    req_ev = next((e.text_content for e in ev_rows if e.evidence_type == "api_request"), "")
    resp_ev = next((e.text_content for e in ev_rows if e.evidence_type == "api_response"), "")
    fatal = (ex.fail_reason or "")[:1500]
    # Local diff highlights (deterministic): failed assertions from actual_result JSON
    highlights: List[str] = []
    try:
        actual_doc = json.loads(ex.actual_result or "{}")
        for fa in (actual_doc.get("failed_assertions") or []):
            highlights.append(f"{fa.get('field')}:{fa.get('target')} {fa.get('operator')} "
                              f"expected={fa.get('expected')!r} actual={fa.get('actual')!r}")
    except Exception:
        pass
    clean_ctx, _ = R.redact_for_ai({
        "expected_status": cfg.expected_status if cfg else None,
        "fail_reason": fatal, "failed_assertions": highlights[:10],
        "response_excerpt": (resp_ev or "")[:1500], "request_excerpt": (req_ev or "")[:800],
    })
    prompt = f"""Triage this API failure. Facts only.

Test: {tc.title if tc else ''} ({tc.tc_code if tc else ''})
Context: {json.dumps(clean_ctx, ensure_ascii=False, default=str)[:3000]}

Return strict JSON:
{{"bucket": "Possible Application Issue | Possible Test Configuration Issue | Possible Environment Issue | Unknown",
  "reasoning": "2-3 sentences, no root-cause claim",
  "suggested_next_steps": ["..."]}}"""
    parsed = await generate_qa_json(prompt, ANALYZE_SYSTEM, preferred_provider, model, max_tokens=800)
    bucket = (parsed.get("bucket") if isinstance(parsed, dict) else None) or "Unknown"
    allowed = {"Possible Application Issue", "Possible Test Configuration Issue",
               "Possible Environment Issue", "Unknown"}
    if bucket not in allowed:
        bucket = "Unknown"
    return {"bucket": bucket,
            "reasoning": (parsed.get("reasoning") if isinstance(parsed, dict) else "") or "",
            "suggested_next_steps": (parsed.get("suggested_next_steps") if isinstance(parsed, dict) else []) or [],
            "diff_highlights": highlights}
