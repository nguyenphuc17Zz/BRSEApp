"""AI script generation grounded ONLY on approved element mappings.

If an element has no ACTIVE mapping, the step is flagged Selector Required —
the AI must never invent a selector.
"""
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.qa.models import TestCase, TestStep
from app.qa.ui_models import UIAutomationScript, UIAutomationScriptHistory, UIElementMapping, UIPageKnowledge
from app.qa import engines as E1
from app.qa.llm import generate_qa_json
from app.qa.api_testing import redact as R
from app.qa.ui_testing import locator_policy as LP

GENERATE_SYSTEM = (
    "You are a senior QA automation engineer writing Playwright UI test flows. "
    "Use ONLY the provided element mappings (by mapping_id). "
    "If a step needs an element with no mapping, set selector_required=true and "
    "describe the element — NEVER invent a selector. "
    "Prefer assertions that verify visible outcomes (text visible, URL changed, "
    "dialog opened). No hard waits; rely on auto-wait. "
    "Test data must use {{VARIABLES}}, never real credentials."
)

ACTION_VOCAB = ("open, navigate, fill, click, select, check, press, upload, "
                "verify_text, verify_visible, verify_hidden, verify_url, "
                "verify_enabled, verify_disabled, verify_value, verify_count")


async def generate_ui_flow(
    db: AsyncSession, test_case_id: str,
    preferred_provider: Optional[str] = None, model: Optional[str] = None,
    changed_by: str = "user",
) -> Dict[str, Any]:
    tc = (await db.execute(select(TestCase).where(TestCase.id == test_case_id))).scalars().first()
    if not tc:
        raise ValueError("Test case not found")
    steps = (await db.execute(select(TestStep).where(
        TestStep.test_case_id == test_case_id).order_by(TestStep.step_order))).scalars().all()
    req = await E1.get_requirement(db, tc.requirement_id) if tc.requirement_id else None

    mappings = (await db.execute(select(UIElementMapping).where(
        UIElementMapping.project_id == tc.project_id,
        UIElementMapping.status == "ACTIVE").order_by(
        UIElementMapping.page_name, UIElementMapping.element_name).limit(120))).scalars().all()
    pages = (await db.execute(select(UIPageKnowledge).where(
        UIPageKnowledge.project_id == tc.project_id).limit(30))).scalars().all()

    map_lines = []
    for m in mappings:
        try:
            loc = json.loads(m.locator_json or "{}")
        except Exception:
            loc = {}
        map_lines.append(
            f"- [{m.id}] {m.page_name} / {m.element_name}: "
            f"{loc.get('strategy')}:{loc.get('value')}")
    page_lines = [f"- {p.page_name}: {p.url_path} — {p.description[:120]}" for p in pages]
    step_lines = [f"{s.step_order}. Action: {s.action} | Expected: {s.expected}" for s in steps]

    prompt = f"""Convert this manual test case into a Playwright UI flow.

Test case [{tc.tc_code}]: {tc.title}
Preconditions: {tc.preconditions}
Steps:
{chr(10).join(step_lines) or '(no structured steps — derive from title/purpose)'}
Expected result: {tc.expected_result}
Requirement: {(req.title if req else '')} — {(req.description if req else '')[:600]}

Known pages:
{chr(10).join(page_lines) or '(none documented)'}

Approved element mappings (ONLY these mapping_ids may be referenced):
{chr(10).join(map_lines) or '(none yet — flag every element step as selector_required)'}

Actions vocabulary: {ACTION_VOCAB}

Return strict JSON:
{{
  "flow": [
    {{"label": "Open Login", "action": "open", "value": "{{{{WEB_BASE_URL}}}}/login"}},
    {{"label": "Enter username", "action": "fill", "mapping_id": "<id>", "value": "{{{{TEST_USER}}"}}"}},
    {{"label": "Verify error", "action": "verify_text", "mapping_id": "<id>", "value": "expected message",
      "assertion_source": "expected|acceptance_criteria|requirement|ai_suggested"}}
  ],
  "unmapped_elements": [{{"label": "...", "description": "which element, where"}}],
  "manual_preferred": false,
  "manual_preferred_reason": ""
}}
Rules: steps needing an element without mapping MUST use {{"selector_required": true, "element_hint": "..."}} instead of mapping_id.
Set manual_preferred=true for visual-subjective/exploratory/one-time/unstable cases."""
    clean_req = {"title": req.title if req else "", "description": (req.description if req else "")[:600]}
    _clean, _had = R.redact_for_ai({"prompt_context": clean_req})
    parsed = await generate_qa_json(prompt, GENERATE_SYSTEM, preferred_provider, model, max_tokens=2500)
    raw_flow = parsed.get("flow", []) if isinstance(parsed, dict) else []

    flow: List[Dict[str, Any]] = []
    by_id = {m.id: m for m in mappings}
    for i, s in enumerate(raw_flow[:40]):
        if not isinstance(s, dict):
            continue
        mid = s.get("mapping_id")
        entry: Dict[str, Any] = {
            "order": i + 1, "label": str(s.get("label") or s.get("action") or f"Step {i + 1}"),
            "action": str(s.get("action") or "click").lower(),
            "value": s.get("value", ""),
            "assertion_source": s.get("assertion_source") or "expected",
        }
        if mid and mid in by_id:
            m = by_id[mid]
            try:
                loc = json.loads(m.locator_json or "{}")
            except Exception:
                loc = {}
            entry["mapping_id"] = mid
            entry["target"] = {"strategy": loc.get("strategy", "text"),
                               "value": loc.get("value", ""),
                               "options": loc.get("options") or {}}
            m.used_count = (m.used_count or 0) + 1
        else:
            entry["selector_required"] = True
            entry["element_hint"] = str(s.get("element_hint") or s.get("label") or "element mapping needed")
        flow.append(entry)

    if not flow:
        # Deterministic fallback: one open step so the script is never empty
        flow = [{"order": 1, "label": "Open application", "action": "open",
                 "value": "{{WEB_BASE_URL}}/", "selector_required": False, "target": {}}]

    ok, problems = LP.validate_flow(flow)
    script_text = LP.render_flow_as_python(flow)

    script = (await db.execute(select(UIAutomationScript).where(
        UIAutomationScript.test_case_id == test_case_id))).scalars().first()
    if not script:
        script = UIAutomationScript(test_case_id=test_case_id)
        db.add(script)
        await db.flush()
    new_version = (script.script_version or 0) + 1
    script.flow_json = json.dumps(flow, ensure_ascii=False)
    script.script_text = script_text
    script.script_version = new_version
    needs_mapping = any(s.get("selector_required") for s in flow)
    manual_pref = bool(parsed.get("manual_preferred")) if isinstance(parsed, dict) else False
    script.status = "REVIEW_REQUIRED"  # AI output is never auto-approved
    script.manual_preferred = manual_pref
    script.manual_preferred_reason = str(parsed.get("manual_preferred_reason") or "") if isinstance(parsed, dict) else ""
    script.updated_by = changed_by
    script.update_reason = "AI generated" + (" (needs element mapping)" if needs_mapping else "")
    try:
        import playwright as _pw
        script.playwright_version = getattr(_pw, "__version__", "")
    except Exception:
        pass
    db.add(UIAutomationScriptHistory(
        test_case_id=test_case_id, version=new_version, script_text=script_text,
        flow_json=json.dumps(flow, ensure_ascii=False),
        reason=script.update_reason, changed_by=changed_by))
    await db.commit()
    await db.refresh(script)
    return {"test_case_id": test_case_id, "version": new_version,
            "status": script.status, "flow": flow,
            "needs_mapping": needs_mapping, "policy_problems": problems,
            "unmapped_elements": parsed.get("unmapped_elements", []) if isinstance(parsed, dict) else [],
            "policy_ok": ok}
