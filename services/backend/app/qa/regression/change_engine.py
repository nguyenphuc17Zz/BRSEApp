"""Change records: user-created from 10 sources, AI-assisted summary/classification.

Also owns requirement versioning (v1 -> v2 -> v3) and change auto-suggest hooks.
"""
import json
import re
from typing import Any, Dict, List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.intelligence.models import WorkItem, ProjectRelationship
from app.qa.models import AcceptanceCriterion
from app.qa.regression_models import ChangeRecord, RequirementVersion
from app.qa import engines as E1
from app.qa.llm import generate_qa_json

VALID_SOURCES = {
    "requirement_update", "spec", "decision", "meeting", "ac_change",
    "api_spec", "ui_change", "bug_fix", "change_request", "document",
}
VALID_CATEGORIES = {
    "NEW_FEATURE", "BEHAVIOR_CHANGE", "VALIDATION_CHANGE", "UI_CHANGE",
    "API_CHANGE", "DATA_CHANGE", "PERMISSION_CHANGE", "BUG_FIX",
    "CONFIG_CHANGE", "DOCUMENT_ONLY", "UNKNOWN",
}
VALID_RISK = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}

CLASSIFY_SYSTEM = (
    "You are a senior BA classifying a software change. "
    "Pick all fitting categories. Distinguish Confirmed (stated in evidence) "
    "from Possible. Never invent business rules."
)


async def next_change_code(db: AsyncSession, project_id: str) -> str:
    res = await db.execute(select(ChangeRecord.change_code).where(
        ChangeRecord.project_id == project_id))
    max_n = 0
    for (code,) in res.all():
        m = re.search(r"(\d+)$", code or "")
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"CR-{max_n + 1:03d}"


def snapshot_requirement(item: WorkItem, acs: List[AcceptanceCriterion]) -> Dict[str, Any]:
    return {
        "title": item.title, "description": item.description,
        "status": item.status, "priority": item.priority,
        "version": item.version,
        "acceptance_criteria": [
            {"ac_code": a.ac_code, "given": a.given_text,
             "when": a.when_text, "then": a.then_text, "status": a.status}
            for a in (acs or [])],
    }


async def save_requirement_version(db: AsyncSession, requirement_id: str,
                                   source: str, changed_by: str = "user") -> RequirementVersion:
    item = await E1.get_requirement(db, requirement_id)
    if not item or item.item_type != "REQUIREMENT":
        raise ValueError("Requirement not found")
    acs = (await db.execute(select(AcceptanceCriterion).where(
        AcceptanceCriterion.requirement_id == requirement_id))).scalars().all()
    last_no = (await db.execute(select(func.max(RequirementVersion.version_no)).where(
        RequirementVersion.requirement_id == requirement_id))).scalar() or 0
    ver = RequirementVersion(
        requirement_id=requirement_id, version_no=last_no + 1,
        title=item.title, description=item.description or "",
        ac_snapshot_json=json.dumps(
            [{"ac_code": a.ac_code, "given": a.given_text,
              "when": a.when_text, "then": a.then_text} for a in acs],
            ensure_ascii=False),
        source=source, created_by=changed_by)
    db.add(ver)
    item.version = (item.version or 1) + 1 if last_no else max(item.version or 1, 1)
    if last_no == 0:
        item.version = 1
    else:
        item.version = last_no + 1
    await db.flush()
    await db.refresh(ver)
    return ver


async def classify_change(old: Dict[str, Any], new: Dict[str, Any],
                          hint: str = "",
                          preferred_provider: Optional[str] = None,
                          model: Optional[str] = None) -> Dict[str, Any]:
    """Rule-first classification, LLM refines. Returns {categories, business_summary}."""
    text = json.dumps(new, ensure_ascii=False).lower()
    cats: set = set()
    if any(k in text for k in ["permission", "role", "権限", "quyền", "admin"]):
        cats.add("PERMISSION_CHANGE")
    if any(k in text for k in ["valid", "required", "バリデーション", "検証", "kiểm tra", "format"]):
        cats.add("VALIDATION_CHANGE")
    if any(k in text for k in ["api", "endpoint", "レスポンス", "status code"]):
        cats.add("API_CHANGE")
    if any(k in text for k in ["screen", "画面", "ui", "button", "màn hình", "layout"]):
        cats.add("UI_CHANGE")
    if any(k in text for k in ["fix", "bug", "不具合", "sửa lỗi", "修正"]):
        cats.add("BUG_FIX")
    prompt = f"""Classify this software change. Old: {json.dumps(old, ensure_ascii=False)[:1500]}
New: {json.dumps(new, ensure_ascii=False)[:1500]}
Hint: {hint[:500]}
Rule-based pre-categories: {sorted(cats) or ['(none)']}
Return strict JSON: {{"categories": ["..."], "business_summary": "Before: ... After: ... Impact: ... (2-4 sentences)"}}"""
    parsed = await generate_qa_json(prompt, CLASSIFY_SYSTEM,
                                    preferred_provider, model, max_tokens=800)
    llm_cats = []
    summary = ""
    if isinstance(parsed, dict) and parsed:
        llm_cats = [c for c in (parsed.get("categories") or []) if c in VALID_CATEGORIES]
        summary = str(parsed.get("business_summary") or "")
    final = sorted(cats | set(llm_cats)) or ["UNKNOWN"]
    if not summary:
        summary = f"Before: {str(old.get('title', ''))[:200]} After: {str(new.get('title', ''))[:200]}"
    return {"categories": final, "business_summary": summary}


async def create_change(
    db: AsyncSession, project_id: str, payload: Dict[str, Any],
    changed_by: str = "user",
) -> ChangeRecord:
    """Creates a ChangeRecord with snapshots, classification, and requirement versioning."""
    source = (payload.get("source") or "requirement_update").lower()
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid source: {source}")
    req_id = payload.get("requirement_id")
    old_snap: Dict[str, Any] = payload.get("old_snapshot") or {}
    new_snap: Dict[str, Any] = payload.get("new_snapshot") or {}
    if req_id and not new_snap:
        item = await E1.get_requirement(db, req_id)
        if not item:
            raise ValueError("Requirement not found")
        acs = (await db.execute(select(AcceptanceCriterion).where(
            AcceptanceCriterion.requirement_id == req_id))).scalars().all()
        new_snap = snapshot_requirement(item, acs)
    if req_id and not old_snap:
        last_ver = (await db.execute(select(RequirementVersion).where(
            RequirementVersion.requirement_id == req_id).order_by(
            RequirementVersion.version_no.desc()).limit(1))).scalars().first()
        if last_ver:
            old_snap = {"title": last_ver.title, "description": last_ver.description,
                        "acceptance_criteria": json.loads(last_ver.ac_snapshot_json or "[]")}
    cls = await classify_change(old_snap, new_snap, payload.get("hint") or "",
                                payload.get("preferred_provider"), payload.get("model"))
    change = ChangeRecord(
        project_id=project_id, change_code=await next_change_code(db, project_id),
        source=source, requirement_id=req_id,
        decision_id=payload.get("decision_id"), bug_id=payload.get("bug_id"),
        old_snapshot_json=json.dumps(old_snap, ensure_ascii=False),
        new_snapshot_json=json.dumps(new_snap, ensure_ascii=False),
        change_summary=(payload.get("change_summary") or cls["business_summary"])[:2000],
        business_summary=cls["business_summary"][:2000],
        categories_json=json.dumps(cls["categories"], ensure_ascii=False),
        risk_level="MEDIUM", risk_reasons_json="[]",
        status="DRAFT", created_by=changed_by)
    db.add(change)
    await db.flush()
    if req_id:
        try:
            await save_requirement_version(db, req_id, f"change:{change.id}", changed_by)
        except ValueError as e:
            logger.warning(f"Version snapshot skipped: {e}")
    await db.commit()
    await db.refresh(change)
    return change


async def suggest_changes(db: AsyncSession, project_id: str) -> List[Dict[str, Any]]:
    """Auto-suggests unrecorded changes: recently updated requirements/bugs/decisions/specs.

    Heuristic: WorkItems updated in last 7 days with no ChangeRecord pointing at them.
    """
    import datetime as _dt
    since = _dt.datetime.utcnow() - _dt.timedelta(days=7)
    items = (await db.execute(select(WorkItem).where(
        WorkItem.project_id == project_id,
        WorkItem.item_type.in_(["REQUIREMENT", "DECISION", "BUG"]),
        WorkItem.updated_at >= since).order_by(WorkItem.updated_at.desc()).limit(30)
    )).scalars().all()
    recorded_req = set((await db.execute(select(ChangeRecord.requirement_id).where(
        ChangeRecord.project_id == project_id,
        ChangeRecord.requirement_id.isnot(None)))).scalars().all())
    recorded_bug = set((await db.execute(select(ChangeRecord.bug_id).where(
        ChangeRecord.project_id == project_id,
        ChangeRecord.bug_id.isnot(None)))).scalars().all())
    out = []
    for it in items:
        if it.item_type == "REQUIREMENT" and it.id in recorded_req:
            continue
        if it.item_type == "BUG" and (it.id in recorded_bug or it.status not in ("DONE", "IN_PROGRESS")):
            continue
        if it.item_type == "DECISION" and it.status != "CONFIRMED":
            continue
        src = {"REQUIREMENT": "requirement_update", "DECISION": "decision",
               "BUG": "bug_fix"}[it.item_type]
        out.append({"work_item_id": it.id, "item_type": it.item_type,
                    "title": it.title, "suggested_source": src,
                    "updated_at": it.updated_at.isoformat() if it.updated_at else ""})
    return out
