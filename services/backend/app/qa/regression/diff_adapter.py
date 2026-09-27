"""Diff adapter: reuses DiffAnalyzer (LLM semantic) + deterministic AC comparison.

Answers the 7 business-meaning questions (§4) and spec v1/v2 breakdown (§5).
"""
import json
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.brain.diff_analyzer import DiffAnalyzer
from app.qa.llm import generate_qa_json

MEANING_SYSTEM = (
    "You are a senior BA. Given a requirement diff, judge which business aspects "
    "changed. Answer only from evidence. If unclear, say so — never guess."
)


async def requirement_before_after(
    db: AsyncSession, change_id: str,
    preferred_provider: Optional[str] = None, model: Optional[str] = None,
) -> Dict[str, Any]:
    """Runs DiffAnalyzer on snapshots, then classifies business meaning."""
    from app.qa.regression_models import ChangeRecord
    from sqlalchemy import select
    change = (await db.execute(select(ChangeRecord).where(
        ChangeRecord.id == change_id))).scalars().first()
    if not change:
        raise ValueError("Change not found")
    old = json.loads(change.old_snapshot_json or "{}")
    new = json.loads(change.new_snapshot_json or "{}")

    def _text(snap: Dict[str, Any]) -> str:
        lines = [f"Title: {snap.get('title', '')}", f"Description: {snap.get('description', '')}"]
        for ac in (snap.get("acceptance_criteria") or []):
            lines.append(f"AC {ac.get('ac_code', '')}: Given {ac.get('given', '')} "
                         f"When {ac.get('when', '')} Then {ac.get('then', '')}")
        return "\n".join(lines)

    diff = await DiffAnalyzer.compare_versions(
        _text(old), _text(new),
        f"Requirement change {change.change_code}",
        provider_name=preferred_provider or "gemini", model=model)
    prompt = f"""Requirement diff: {json.dumps(diff, ensure_ascii=False)[:3000]}
For each aspect answer changed=true/false with one-line evidence:
business_meaning, validation, expected_behavior, permission, state, input, output.
Return strict JSON: {{"aspects": [{{"aspect": "...", "changed": true, "evidence": "..."}}]}}"""
    parsed = await generate_qa_json(prompt, MEANING_SYSTEM,
                                    preferred_provider, model, max_tokens=800)
    aspects = []
    if isinstance(parsed, dict) and isinstance(parsed.get("aspects"), list):
        for a in parsed["aspects"]:
            if isinstance(a, dict) and a.get("aspect"):
                aspects.append({"aspect": str(a["aspect"]),
                                "changed": bool(a.get("changed")),
                                "evidence": str(a.get("evidence") or "")[:300]})
    if not aspects:
        # Deterministic fallback: title/description/AC-level signals
        aspects = _fallback_aspects(old, new)
    return {"change_id": change.id, "change_code": change.change_code,
            "diff": diff, "aspects": aspects}


def _fallback_aspects(old: Dict[str, Any], new: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    out.append({"aspect": "business_meaning",
                "changed": old.get("title") != new.get("title"),
                "evidence": "Title changed" if old.get("title") != new.get("title") else "Title identical"})
    out.append({"aspect": "expected_behavior",
                "changed": old.get("description") != new.get("description"),
                "evidence": "Description changed" if old.get("description") != new.get("description") else "Description identical"})
    old_acs = {a.get("ac_code"): a for a in (old.get("acceptance_criteria") or [])}
    new_acs = {a.get("ac_code"): a for a in (new.get("acceptance_criteria") or [])}
    ac_changed = (set(old_acs) != set(new_acs) or
                  any(old_acs[k] != new_acs.get(k) for k in old_acs if k in new_acs))
    out.append({"aspect": "validation",
                "changed": ac_changed,
                "evidence": "AC set changed" if ac_changed else "AC set identical"})
    for aspect in ("permission", "state", "input", "output"):
        out.append({"aspect": aspect, "changed": False,
                    "evidence": "Needs Review — insufficient evidence for automatic judgment"})
    return out


async def spec_versions_diff(old_text: str, new_text: str, label: str = "Spec v1 vs v2",
                             preferred_provider: Optional[str] = None,
                             model: Optional[str] = None) -> Dict[str, Any]:
    """Spec-level diff reusing DiffAnalyzer, normalized to §5 buckets."""
    diff = await DiffAnalyzer.compare_versions(
        old_text, new_text, label,
        provider_name=preferred_provider or "gemini", model=model)
    buckets: Dict[str, List[Any]] = {
        "requirement_added": [], "requirement_removed": [],
        "requirement_changed": [], "acceptance_criteria_changed": [],
        "field_changed": [], "validation_changed": [],
        "screen_changed": [], "api_changed": [], "business_rule_changed": [],
    }

    def _bucket(item_text: str) -> str:
        t = (item_text or "").lower()
        if any(k in t for k in ["api", "endpoint", "レスポンス", "リクエスト"]):
            return "api_changed"
        if any(k in t for k in ["screen", "画面", "ui", "button", "màn hình"]):
            return "screen_changed"
        if any(k in t for k in ["valid", "required", "バリデーション", "検証"]):
            return "validation_changed"
        if any(k in t for k in ["field", "column", "項目", "trường"]):
            return "field_changed"
        if any(k in t for k in ["acceptance", "given", "when", "then", "受け入れ"]):
            return "acceptance_criteria_changed"
        if any(k in t for k in ["rule", "business", "ルール", "仕様"]):
            return "business_rule_changed"
        return "requirement_changed"

    for item in (diff.get("added") or []):
        buckets["requirement_added"].append(item)
    for item in (diff.get("removed") or []):
        buckets["requirement_removed"].append(item)
    for item in (diff.get("modified") or []):
        buckets[_bucket(json.dumps(item, ensure_ascii=False))].append(item)
    return {"diff": diff, "buckets": buckets}
