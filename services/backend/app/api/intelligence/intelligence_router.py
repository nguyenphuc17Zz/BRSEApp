import json
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from app.core.database import get_db
from app.core.logging import logger
from app.intelligence.extractors.conversation_analyzer import ConversationAnalyzer
from app.intelligence.extractors.requirement_extractor import RequirementExtractor
from app.intelligence.extractors.bug_analyzer import BugAnalyzer
from app.intelligence.extractors.decision_extractor import DecisionExtractor
from app.intelligence.extractors.todo_extractor import TodoExtractor
from app.intelligence.extractors.meeting_analyzer import MeetingAnalyzer
from app.intelligence.brain.ask_project import AskProjectEngine
from app.intelligence.brain.ask_meetings import AskMeetingsEngine
from app.intelligence.brain.diff_analyzer import DiffAnalyzer
from app.intelligence.brain.impact_analyzer import ImpactAnalyzer
from app.intelligence.reply.advanced_reply import AdvancedReplyEngine
from app.intelligence.automation.policy_engine import policy_engine
from app.intelligence.models import WorkItem, WorkItemEvidence, MeetingRecord

router = APIRouter(prefix="/api/intelligence", tags=["BrSE Intelligence"])

class AnalyzeRequest(BaseModel):
    text: str
    project_id: str
    source_type: str = "manual" # slack, line, manual, meeting
    source_id: str = "chat-1"
    author: Optional[str] = "Team"
    save_drafts: bool = True

class MeetingAnalyzeRequest(BaseModel):
    project_id: str
    title: str
    meeting_date: str
    transcript_text: str
    participants: List[str] = []
    preferred_provider: Optional[str] = None
    model: Optional[str] = None

class ExtractionRequest(BaseModel):
    text: str
    project_id: str
    source_type: str = "manual"
    source_id: str = "manual-1"
    preferred_provider: Optional[str] = None
    model: Optional[str] = None

class AskProjectRequest(BaseModel):
    query: str
    chat_history: Optional[List[Dict[str, str]]] = None
    scope: Optional[str] = "all"
    provider_name: Optional[str] = None
    preferred_provider: Optional[str] = None
    model_name: Optional[str] = None
    model: Optional[str] = None

class AskMeetingsRequest(BaseModel):
    project_id: Optional[str] = None
    query: str
    preferred_provider: Optional[str] = None
    model: Optional[str] = None
    chat_history: Optional[List[Dict[str, str]]] = None


class DiffRequest(BaseModel):
    old_text: str
    new_text: str
    title: str = "Document Revision"

class ImpactRequest(BaseModel):
    change_description: str
    affected_component: str = "Authentication"

class ReplyGenerateRequest(BaseModel):
    current_message: str
    conversation_context: Optional[List[str]] = None
    project_id: Optional[str] = None
    user_style: str = "standard_business"

@router.post("/analyze")
async def analyze_conversation(payload: AnalyzeRequest, db: AsyncSession = Depends(get_db)):
    """Analyzes a conversation or message thread.
    Extracts summary, timeline, requirements, bugs, decisions, TODOs, risks, and open questions.
    Preserves all evidence and flags conflicts.
    """
    messages = [
        {
            "sender": payload.author or "User",
            "text": payload.text,
            "timestamp": "Recent"
        }
    ]
    analysis = await ConversationAnalyzer.analyze_conversation(
        messages=messages,
        project_name=f"Project {payload.project_id}"
    )

    created_work_items = []
    if payload.save_drafts:
        # 1. Extract requirements with conflict detection
        req_results = await RequirementExtractor.extract_and_validate(
            db=db,
            project_id=payload.project_id,
            source_text=payload.text,
            source_type=payload.source_type,
            source_id=payload.source_id,
            author=payload.author
        )
        for r in req_results:
            created_work_items.append(r["id"])

        # 2. Extract bug if present
        bug_item = await BugAnalyzer.extract_bug(
            db=db,
            project_id=payload.project_id,
            source_text=payload.text,
            source_type=payload.source_type,
            source_id=payload.source_id,
            author=payload.author
        )
        if bug_item:
            created_work_items.append(bug_item.id)

        # 3. Extract decision if present
        dec_item = await DecisionExtractor.extract_decision(
            db=db,
            project_id=payload.project_id,
            source_text=payload.text,
            source_type=payload.source_type,
            source_id=payload.source_id,
            author=payload.author
        )
        if dec_item:
            created_work_items.append(dec_item.id)

        # 4. Extract TODOs
        todos = await TodoExtractor.extract_todos(
            db=db,
            project_id=payload.project_id,
            source_text=payload.text,
            source_type=payload.source_type,
            source_id=payload.source_id,
            author=payload.author
        )
        for t in todos:
            created_work_items.append(t.id)

        # Level 2 Automation: Evaluates rules and saves non-silent audit log
        await policy_engine.evaluate_event(
            db=db,
            event_trigger="message_received",
            event_data={
                "source_type": payload.source_type,
                "source_id": payload.source_id,
                "text": payload.text,
                "confidence": 0.90,
                "intents": ["QUESTION"] if ("?" in payload.text or "か" in payload.text) else ["NORMAL"]
            },
            project_id=payload.project_id
        )

    return {
        "status": "success",
        "analysis": analysis,
        "created_work_item_ids": created_work_items
    }

@router.post("/meetings/analyze")
async def analyze_meeting(payload: MeetingAnalyzeRequest, db: AsyncSession = Depends(get_db)):
    """Analyzes a meeting transcript, extracts structured business notes, action items, decisions."""
    try:
        record = await MeetingAnalyzer.analyze_meeting(
            db=db,
            project_id=payload.project_id,
            title=payload.title,
            meeting_date=payload.meeting_date,
            transcript_text=payload.transcript_text,
            provider_name=payload.preferred_provider or "groq",
            model=payload.model
        )

        # Real-time synchronization to BrSE Workspace Work Items
        try:
            from app.intelligence.sync_cleanup_service import sync_single_meeting_to_work_items
            await sync_single_meeting_to_work_items(db, record)
            await db.commit()
        except Exception as se:
            logger.warning(f"Failed auto-syncing newly analyzed meeting to work items: {se}")

        summary_ja = ""
        summary_vi = ""
        summary_md = record.summary_markdown
        try:
            s_obj = json.loads(record.summary_markdown or "{}")
            if isinstance(s_obj, dict) and ("ja" in s_obj or "vi" in s_obj):
                summary_ja = s_obj.get("ja", "")
                summary_vi = s_obj.get("vi", "")
                summary_md = summary_vi or summary_ja
        except Exception:
            summary_vi = record.summary_markdown
            summary_ja = record.summary_markdown

        return {
            "id": record.id,
            "project_id": record.project_id,
            "title": record.title,
            "meeting_date": record.meeting_date,
            "participants": json.loads(record.participants_json or "[]"),
            "summary_markdown": summary_md,
            "summary_ja": summary_ja,
            "summary_vi": summary_vi,
            "decisions": json.loads(record.decisions_json or "[]"),
            "action_items": json.loads(record.action_items_json or "[]"),
            "open_questions": json.loads(record.open_questions_json or "[]")
        }
    except Exception as e:
        logger.exception(f"Error in analyze_meeting: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/meetings")
async def list_meetings(project_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Lists saved meeting records for a project (or all if not specified)."""
    stmt = select(MeetingRecord)
    if project_id and project_id not in ("all", "default-project"):
        stmt = stmt.where(MeetingRecord.project_id == project_id)
    stmt = stmt.order_by(MeetingRecord.created_at.desc())
    res = await db.execute(stmt)
    records = res.scalars().all()
    out = []
    for r in records:
        summary_ja = ""
        summary_vi = ""
        summary_md = r.summary_markdown
        try:
            s_obj = json.loads(r.summary_markdown or "{}")
            if isinstance(s_obj, dict) and ("ja" in s_obj or "vi" in s_obj):
                summary_ja = s_obj.get("ja", "")
                summary_vi = s_obj.get("vi", "")
                summary_md = summary_vi or summary_ja
        except Exception:
            summary_vi = r.summary_markdown
            summary_ja = r.summary_markdown

        out.append({
            "id": r.id,
            "project_id": r.project_id,
            "title": r.title,
            "meeting_date": r.meeting_date,
            "participants": json.loads(r.participants_json or "[]"),
            "summary_markdown": summary_md,
            "summary_ja": summary_ja,
            "summary_vi": summary_vi,
            "decisions": json.loads(r.decisions_json or "[]"),
            "action_items": json.loads(r.action_items_json or "[]"),
            "open_questions": json.loads(r.open_questions_json or "[]"),
            "created_at": r.created_at.isoformat() if r.created_at else ""
        })
    return out

@router.post("/meetings/ask")
async def ask_meetings(payload: AskMeetingsRequest, db: AsyncSession = Depends(get_db)):
    """Cross-Meeting Brain Q&A: Synthesizes answers and decision evolutions across all meetings."""
    res = await AskMeetingsEngine.ask_meetings(
        db=db,
        project_id=payload.project_id,
        question=payload.query,
        chat_history=payload.chat_history,
        provider_name=payload.preferred_provider or "groq",
        model=payload.model
    )
    return res


@router.delete("/meetings/clear-all")
async def clear_all_meetings(db: AsyncSession = Depends(get_db)):
    """Deletes all test meeting records, associated meeting evidence, and orphaned draft work items."""
    stmt_prop = select(WorkItem.id).join(WorkItemEvidence, WorkItem.id == WorkItemEvidence.work_item_id).where(
        WorkItem.status == "PROPOSED",
        WorkItemEvidence.source_type == "meeting"
    )
    prop_ids = list(set((await db.execute(stmt_prop)).scalars().all()))

    await db.execute(delete(WorkItemEvidence).where(WorkItemEvidence.source_type == "meeting"))
    
    deleted_drafts = 0
    for pid in prop_ids:
        other_ev = (await db.execute(
            select(func.count(WorkItemEvidence.id)).where(WorkItemEvidence.work_item_id == pid)
        )).scalar_one()
        if other_ev == 0:
            wi = await db.get(WorkItem, pid)
            if wi:
                await db.delete(wi)
                deleted_drafts += 1

    res = await db.execute(delete(MeetingRecord))
    await db.commit()
    return {
        "message": "All meeting records and orphaned draft work items cleared successfully",
        "deleted_meetings": res.rowcount,
        "deleted_draft_work_items": deleted_drafts
    }

@router.delete("/meetings/{meeting_id}")
async def delete_meeting(meeting_id: str, db: AsyncSession = Depends(get_db)):
    """Deletes a single meeting record, its evidence, and any orphaned draft work items."""
    meeting = await db.get(MeetingRecord, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting record not found")

    # 1. Identify all work items that have evidence from this meeting
    ev_res = await db.execute(
        select(WorkItemEvidence.work_item_id).where(WorkItemEvidence.source_id == meeting_id)
    )
    linked_item_ids = list(set(ev_res.scalars().all()))

    # 2. Delete the evidences
    await db.execute(delete(WorkItemEvidence).where(WorkItemEvidence.source_id == meeting_id))

    # 3. If any linked work item is in PROPOSED status and has no other evidence, delete it
    deleted_drafts = 0
    for wi_id in linked_item_ids:
        wi = await db.get(WorkItem, wi_id)
        if wi and wi.status == "PROPOSED":
            other_ev = (await db.execute(
                select(func.count(WorkItemEvidence.id)).where(WorkItemEvidence.work_item_id == wi_id)
            )).scalar_one()
            if other_ev == 0:
                await db.delete(wi)
                deleted_drafts += 1

    # 4. Delete the meeting record
    await db.delete(meeting)
    await db.commit()
    return {
        "message": "Meeting, evidence, and orphaned draft work items deleted successfully",
        "id": meeting_id,
        "deleted_draft_work_items": deleted_drafts
    }

# Project Brain Endpoints
@router.get("/projects/{project_id}/brain-stats")
async def get_project_brain_stats(project_id: str, db: AsyncSession = Depends(get_db)):
    """Returns real counts of meetings, work items, decisions, action items, and evidences for the project."""
    effective_pid = project_id if (project_id and project_id not in ("all", "default-project", "")) else None

    stmt_m = select(func.count(MeetingRecord.id))
    stmt_w = select(func.count(WorkItem.id))
    stmt_dec = select(func.count(WorkItem.id)).where(WorkItem.item_type == "DECISION")
    stmt_act = select(func.count(WorkItem.id)).where(WorkItem.item_type.in_(["ACTION", "TODO", "MEETING_ITEM"]))
    stmt_oq = select(func.count(WorkItem.id)).where(WorkItem.item_type.in_(["OPEN_QUESTION", "QUESTION"]))
    stmt_ev = select(func.count(WorkItemEvidence.id))

    if effective_pid:
        stmt_m = stmt_m.where(MeetingRecord.project_id == effective_pid)
        stmt_w = stmt_w.where(WorkItem.project_id == effective_pid)
        stmt_dec = stmt_dec.where(WorkItem.project_id == effective_pid)
        stmt_act = stmt_act.where(WorkItem.project_id == effective_pid)
        stmt_oq = stmt_oq.where(WorkItem.project_id == effective_pid)
        stmt_ev = stmt_ev.join(WorkItem, WorkItemEvidence.work_item_id == WorkItem.id).where(WorkItem.project_id == effective_pid)

    total_meetings = (await db.execute(stmt_m)).scalar() or 0
    total_work_items = (await db.execute(stmt_w)).scalar() or 0
    total_decisions = (await db.execute(stmt_dec)).scalar() or 0
    total_actions = (await db.execute(stmt_act)).scalar() or 0
    total_open_questions = (await db.execute(stmt_oq)).scalar() or 0
    total_evidences = (await db.execute(stmt_ev)).scalar() or 0

    return {
        "project_id": project_id,
        "total_meetings": total_meetings,
        "total_work_items": total_work_items,
        "total_decisions": total_decisions,
        "total_actions": total_actions,
        "total_open_questions": total_open_questions,
        "total_evidences": total_evidences,
        "is_synced": True
    }

@router.post("/projects/{project_id}/ask")
async def ask_project(project_id: str, payload: AskProjectRequest, db: AsyncSession = Depends(get_db)):
    """Ask Project: Evidence-based Multi-turn Q&A across meetings, work items, and evidence quotes."""
    res = await AskProjectEngine.ask_project(
        db=db,
        project_id=project_id,
        question=payload.query,
        chat_history=payload.chat_history,
        scope=payload.scope or "all",
        provider_name=payload.preferred_provider or payload.provider_name or "groq",
        model=payload.model or payload.model_name
    )
    return res

@router.post("/projects/{project_id}/diff")
async def diff_documents(project_id: str, payload: DiffRequest, db: AsyncSession = Depends(get_db)):
    """What Changed? Compares old and new text/specifications for additions, deletions, and potential conflicts."""
    res = await DiffAnalyzer.compare_versions(
        text_before=payload.old_text,
        text_after=payload.new_text,
        context_label=payload.title
    )
    return res

@router.post("/projects/{project_id}/impact")
async def analyze_impact(project_id: str, payload: ImpactRequest, db: AsyncSession = Depends(get_db)):
    """Change Impact Analysis: Predicts APIs, frontend UI, test cases, and specs affected by a requirement change."""
    res = await ImpactAnalyzer.analyze_impact(
        changed_requirement=payload.change_description,
        project_context=f"Component {payload.affected_component}"
    )
    return res

# Advanced Reply Generator
@router.post("/reply/generate")
async def generate_reply(payload: ReplyGenerateRequest, db: AsyncSession = Depends(get_db)):
    """Generates 3 nuanced Japanese business replies with intent classification and commitment fact protection."""
    # Fetch confirmed decisions for project if provided
    decisions_list = []
    if payload.project_id:
        dec_stmt = select(WorkItem).where(
            WorkItem.project_id == payload.project_id,
            WorkItem.item_type == "DECISION",
            WorkItem.status == "CONFIRMED"
        )
        dec_res = await db.execute(dec_stmt)
        dec_items = dec_res.scalars().all()
        decisions_list = [f"{d.title}: {d.description}" for d in dec_items]

    res = await AdvancedReplyEngine.generate_smart_replies(
        incoming_message=payload.current_message,
        conversation_history=payload.conversation_context or [],
        project_name=f"Project {payload.project_id}" if payload.project_id else "Client Project",
        confirmed_decisions=decisions_list
    )
    return res

class RAGIndexRequest(BaseModel):
    project_id: str
    filename: str
    text_content: str
    metadata: Optional[Dict[str, Any]] = None

@router.post("/rag/index-file")
async def rag_index_file(payload: RAGIndexRequest, db: AsyncSession = Depends(get_db)):
    """Indexes a single document or text snippet into Project Document RAG."""
    from app.intelligence.rag.project_rag_service import project_rag_service
    count = await project_rag_service.index_document_text(
        db=db,
        project_id=payload.project_id,
        filename=payload.filename,
        text_content=payload.text_content,
        metadata=payload.metadata
    )
    return {"status": "indexed", "filename": payload.filename, "chunks_created": count}

@router.post("/rag/index-project/{project_id}")
async def rag_index_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """Scans and indexes all project documents into Project Document RAG."""
    from app.intelligence.rag.project_rag_service import project_rag_service
    res = await project_rag_service.index_all_project_documents(db=db, project_id=project_id)
    return res

@router.get("/rag/search")
async def rag_search(
    query: str,
    project_id: Optional[str] = None,
    top_k: int = 6,
    db: AsyncSession = Depends(get_db)
):
    """Searches top relevant chunks across project documents with token budget safety."""
    from app.intelligence.rag.project_rag_service import project_rag_service
    res = await project_rag_service.build_rag_context(db=db, project_id=project_id, query=query, max_tokens=2800)
    return res

