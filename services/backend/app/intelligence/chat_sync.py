import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.models import Project
from app.intelligence.extractors.requirement_extractor import RequirementExtractor
from app.intelligence.extractors.bug_analyzer import BugAnalyzer
from app.intelligence.extractors.decision_extractor import DecisionExtractor
from app.intelligence.extractors.todo_extractor import TodoExtractor
from app.intelligence.automation.policy_engine import policy_engine

async def resolve_effective_project_id(db: AsyncSession, project_id: Optional[str] = None) -> str:
    """Ensures a valid project_id matching database Foreign Key constraint."""
    if project_id and project_id not in ("all", "default-project", ""):
        res = await db.execute(select(Project.id).where(Project.id == project_id))
        val = res.scalar_one_or_none()
        if val:
            return val

    # Lookup first existing project in DB
    first_p = (await db.execute(select(Project.id).limit(1))).scalar_one_or_none()
    if first_p:
        return first_p

    # Fallback to seed project ID
    return "10751429-c6ce-40a3-a700-45df4946909f"

async def sync_chat_message_to_inbox(
    db: AsyncSession,
    text: str,
    source_type: str,
    source_id: str,
    author: str,
    timestamp: Optional[str] = None,
    project_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Ingests an incoming chat message from LINE, Slack, etc.
    Runs multi-layer intelligence extraction (Requirements, Bugs, Decisions, Tasks/Deadlines)
    and saves proposed WorkItems to DB with source evidence links.
    """
    effective_pid = await resolve_effective_project_id(db, project_id)
    time_str = timestamp or datetime.datetime.utcnow().isoformat()
    created_items: List[str] = []

    # 1. Requirements extraction & conflict checking
    try:
        req_results = await RequirementExtractor.extract_and_validate(
            db=db,
            project_id=effective_pid,
            source_text=text,
            source_type=source_type,
            source_id=source_id,
            author=author,
            timestamp=time_str
        )
        for r in req_results:
            created_items.append(r["id"])
    except Exception as e:
        logger.warning(f"Error extracting requirements from {source_type}: {e}")

    # 2. Bug extraction
    try:
        bug_item = await BugAnalyzer.extract_bug(
            db=db,
            project_id=effective_pid,
            source_text=text,
            source_type=source_type,
            source_id=source_id,
            author=author,
            timestamp=time_str
        )
        if bug_item:
            created_items.append(bug_item.id)
    except Exception as e:
        logger.warning(f"Error extracting bug from {source_type}: {e}")

    # 3. Decision extraction
    try:
        dec_item = await DecisionExtractor.extract_decision(
            db=db,
            project_id=effective_pid,
            source_text=text,
            source_type=source_type,
            source_id=source_id,
            author=author,
            timestamp=time_str
        )
        if dec_item:
            created_items.append(dec_item.id)
    except Exception as e:
        logger.warning(f"Error extracting decision from {source_type}: {e}")

    # 4. Action items / Deadlines
    try:
        todos = await TodoExtractor.extract_todos(
            db=db,
            project_id=effective_pid,
            source_text=text,
            source_type=source_type,
            source_id=source_id,
            author=author,
            timestamp=time_str
        )
        for t in todos:
            created_items.append(t.id)
    except Exception as e:
        logger.warning(f"Error extracting todos from {source_type}: {e}")

    # 5. Policy Engine evaluation (Level 2 automation rules)
    try:
        await policy_engine.evaluate_event(
            db=db,
            event_trigger="message_received",
            event_data={
                "source_type": source_type,
                "source_id": source_id,
                "text": text,
                "confidence": 0.90,
                "intents": ["NORMAL"]
            },
            project_id=effective_pid
        )
    except Exception as e:
        logger.warning(f"Policy evaluation error for {source_type}: {e}")

    try:
        await db.commit()
    except Exception as e:
        logger.error(f"Failed committing chat sync work items: {e}")
        await db.rollback()

    logger.info(f"Chat sync [{source_type}] created {len(created_items)} WorkItem drafts for project {effective_pid}")
    return {
        "status": "synced",
        "project_id": effective_pid,
        "created_work_item_ids": created_items,
        "total_created": len(created_items)
    }
