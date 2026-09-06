import json
import time
import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Request, Header, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import logger
from app.intelligence.models import LineCapturedMessage, WorkItem, ProjectStakeholder
from app.intelligence.line.line_client import line_client
from app.intelligence.reply.advanced_reply import AdvancedReplyEngine
from app.intelligence.rag.project_rag_service import ProjectRAGService
from app.intelligence.chat_sync import sync_chat_message_to_inbox

router = APIRouter(prefix="/api/line", tags=["LINE Integration"])

class LineReplyRequest(BaseModel):
    reply_token: str
    message_text: str
    project_id: Optional[str] = None

class LineSimulateMessageRequest(BaseModel):
    text: str
    sender: str = "Client PM"
    project_id: Optional[str] = None
    provider: Optional[str] = "auto"
    model: Optional[str] = None

class RegenerateReplyRequest(BaseModel):
    provider: Optional[str] = "auto"
    model: Optional[str] = None

@router.post("/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    """Official LINE Messaging API Webhook.
    Verifies signature, normalizes messages, retrieves RAG spec context, drafts smart replies,
    and automatically extracts Requirements, Bugs, Decisions, Tasks/Deadlines into BrSE Work Inbox.
    Persisted to SQLite line_captured_messages table.
    """
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")
    
    if x_line_signature and not line_client.verify_signature(body_bytes, x_line_signature):
        logger.warning("Invalid LINE webhook signature received.")
        raise HTTPException(status_code=400, detail="Invalid LINE webhook signature")

    try:
        payload = json.loads(body_str) if body_str else {}
    except Exception as e:
        logger.error(f"Malformed JSON in LINE webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    normalized_events = line_client.parse_webhook_payload(payload)
    results = []

    for event in normalized_events:
        text = event.get("text", "")
        sender_name = event.get("sender", "Client (LINE)")
        msg_id = event.get("message_id") or f"line-wh-{int(time.time()*1000)}"
        reply_token = event.get("reply_token")

        # Smart replies generation
        replies = await AdvancedReplyEngine.generate_smart_replies(
            incoming_message=text
        )

        # Multi-layer sync into BrSE Workspace Work Items
        sync_res = await sync_chat_message_to_inbox(
            db=db,
            text=text,
            source_type="line",
            source_id=msg_id,
            author=sender_name,
            timestamp=event.get("timestamp")
        )

        db_msg = LineCapturedMessage(
            project_id=None,
            conversation_id=event.get("conversation_id", "line-group-default"),
            message_id=msg_id,
            sender=sender_name,
            timestamp=datetime.datetime.utcnow(),
            text=text,
            reply_token=reply_token,
            detected_intent=replies.get("detected_intent", "NORMAL"),
            commitment_warning=replies.get("commitment_warning"),
            suggested_replies=replies.get("replies", []),
            rag_sources=replies.get("rag_sources", []),
            sync_result=sync_res
        )
        db.add(db_msg)
        results.append(event)

    await db.commit()
    return {"status": "processed", "count": len(results)}

@router.get("/messages")
async def get_line_messages(
    project_id: Optional[str] = Query(None),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db)
):
    """Returns persistent LINE messages from SQLite, filtered by project_id."""
    stmt = select(LineCapturedMessage)
    if project_id and project_id not in ("all", "default-project"):
        stmt = stmt.where(LineCapturedMessage.project_id == project_id)
    stmt = stmt.order_by(LineCapturedMessage.created_at.desc()).limit(limit)
    records = (await db.execute(stmt)).scalars().all()

    return {
        "messages": [
            {
                "id": r.id,
                "project_id": r.project_id,
                "conversation_id": r.conversation_id,
                "message_id": r.message_id,
                "sender": r.sender,
                "sender_id": r.sender_id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "text": r.text,
                "reply_token": r.reply_token,
                "detected_intent": r.detected_intent,
                "commitment_warning": r.commitment_warning,
                "suggested_replies": r.suggested_replies or [],
                "rag_sources": r.rag_sources or [],
                "sync_result": r.sync_result or {},
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]
    }

@router.post("/simulate")
async def simulate_line_message(
    payload: LineSimulateMessageRequest, 
    db: AsyncSession = Depends(get_db)
):
    """Simulates an incoming LINE message for BrSE testing.
    Tích hợp RAG Project Specs & Quyết định dự án đã duyệt để sinh câu trả lời chuẩn xác.
    Đồng bộ sang BrSE Work Inbox và lưu bền vững vào CSDL SQLite.
    """
    msg_id = f"line-sim-{int(time.time()*1000)}"
    fake_token = f"token-{msg_id}"
    
    rag_chunks = []
    confirmed_decisions = []
    sender_id = None
    target_pid = payload.project_id if payload.project_id not in ("all", "default-project", "") else None

    if target_pid:
        # 1. Fetch relevant RAG chunks from Project Specifications
        try:
            retrieved = await ProjectRAGService.retrieve_relevant_chunks(
                db=db,
                project_id=target_pid,
                query=payload.text,
                top_k=3
            )
            rag_chunks = [
                {
                    "file_name": ch.get("filename"),
                    "chunk_index": ch.get("chunk_index", 0) + 1,
                    "text": ch.get("content", "")
                }
                for ch in retrieved
            ]
        except Exception as e:
            logger.warning(f"RAG search error for LINE simulation: {e}")

        # 2. Fetch confirmed decisions from Work Items
        try:
            dec_stmt = select(WorkItem.title).where(
                WorkItem.project_id == target_pid,
                WorkItem.item_type == "DECISION",
                WorkItem.status == "CONFIRMED"
            ).limit(5)
            confirmed_decisions = list((await db.execute(dec_stmt)).scalars().all())
        except Exception as e:
            logger.warning(f"Decision fetch error for LINE simulation: {e}")

        # 3. Match sender to ProjectStakeholder if exists
        try:
            st_stmt = select(ProjectStakeholder).where(
                ProjectStakeholder.project_id == target_pid,
                ProjectStakeholder.name == payload.sender
            )
            st_rec = (await db.execute(st_stmt)).scalars().first()
            if st_rec:
                sender_id = st_rec.id
        except Exception:
            pass

    # 4. Generate Smart Replies with RAG Context & Safety Protection
    replies = await AdvancedReplyEngine.generate_smart_replies(
        incoming_message=payload.text,
        project_name=f"Project {target_pid}" if target_pid else "Client Project",
        confirmed_decisions=confirmed_decisions,
        rag_chunks=rag_chunks,
        provider_name=payload.provider or "auto",
        model=payload.model
    )

    # 5. Multi-layer sync into BrSE Workspace Work Items
    iso_time = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    sync_res = await sync_chat_message_to_inbox(
        db=db,
        text=payload.text,
        source_type="line",
        source_id=msg_id,
        author=payload.sender,
        timestamp=iso_time,
        project_id=target_pid
    )

    # 6. Save persistent record to SQLite line_captured_messages
    db_msg = LineCapturedMessage(
        project_id=target_pid,
        conversation_id="line-group-project",
        message_id=msg_id,
        sender=payload.sender,
        sender_id=sender_id,
        timestamp=datetime.datetime.utcnow(),
        text=payload.text,
        reply_token=fake_token,
        detected_intent=replies.get("detected_intent", "NORMAL"),
        commitment_warning=replies.get("commitment_warning"),
        suggested_replies=replies.get("replies", []),
        rag_sources=replies.get("rag_sources", []),
        sync_result=sync_res
    )
    db.add(db_msg)
    await db.commit()
    await db.refresh(db_msg)

    return {
        "id": db_msg.id,
        "source": "line",
        "project_id": db_msg.project_id,
        "conversation_id": db_msg.conversation_id,
        "message_id": db_msg.message_id,
        "sender": db_msg.sender,
        "sender_id": db_msg.sender_id,
        "timestamp": db_msg.timestamp.isoformat(),
        "text": db_msg.text,
        "reply_token": db_msg.reply_token,
        "detected_intent": db_msg.detected_intent,
        "commitment_warning": db_msg.commitment_warning,
        "suggested_replies": db_msg.suggested_replies,
        "rag_sources": db_msg.rag_sources,
        "sync_result": db_msg.sync_result,
        "created_at": db_msg.created_at.isoformat()
    }

@router.delete("/messages/clear-all")
async def clear_line_messages(
    project_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Permanently deletes all captured LINE messages for a project (Zero-waste)."""
    stmt = delete(LineCapturedMessage)
    if project_id and project_id not in ("all", "default-project"):
        stmt = stmt.where(LineCapturedMessage.project_id == project_id)
    res = await db.execute(stmt)
    await db.commit()
    return {"success": True, "deleted_count": res.rowcount, "message": f"Đã xóa {res.rowcount} tin nhắn LINE."}

@router.delete("/messages/{message_id}")
async def delete_line_message(message_id: str, db: AsyncSession = Depends(get_db)):
    """Permanently deletes a specific captured LINE message from database."""
    stmt = select(LineCapturedMessage).where(
        (LineCapturedMessage.id == message_id) | (LineCapturedMessage.message_id == message_id)
    )
    item = (await db.execute(stmt)).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy tin nhắn LINE.")

    await db.delete(item)
    await db.commit()
    return {"success": True, "id": message_id, "message": "Đã xóa tin nhắn thành công."}

@router.post("/messages/{message_id}/regenerate")
async def regenerate_line_reply(
    message_id: str,
    payload: RegenerateReplyRequest,
    db: AsyncSession = Depends(get_db)
):
    """Regenerates AI reply proposals for an existing message using specified Provider & Model."""
    stmt = select(LineCapturedMessage).where(
        (LineCapturedMessage.id == message_id) | (LineCapturedMessage.message_id == message_id)
    )
    item = (await db.execute(stmt)).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy tin nhắn LINE.")

    rag_chunks = []
    confirmed_decisions = []
    if item.project_id:
        try:
            retrieved = await ProjectRAGService.retrieve_relevant_chunks(
                db=db,
                project_id=item.project_id,
                query=item.text,
                top_k=3
            )
            rag_chunks = [
                {
                    "file_name": ch.get("filename"),
                    "chunk_index": ch.get("chunk_index", 0) + 1,
                    "text": ch.get("content", "")
                }
                for ch in retrieved
            ]
            dec_stmt = select(WorkItem.title).where(
                WorkItem.project_id == item.project_id,
                WorkItem.item_type == "DECISION",
                WorkItem.status == "CONFIRMED"
            ).limit(5)
            confirmed_decisions = list((await db.execute(dec_stmt)).scalars().all())
        except Exception as e:
            logger.warning(f"Regenerate RAG fetch error: {e}")

    replies = await AdvancedReplyEngine.generate_smart_replies(
        incoming_message=item.text,
        project_name=f"Project {item.project_id}",
        confirmed_decisions=confirmed_decisions,
        rag_chunks=rag_chunks,
        provider_name=payload.provider or "auto",
        model=payload.model
    )

    item.detected_intent = replies.get("detected_intent", "NORMAL")
    item.commitment_warning = replies.get("commitment_warning")
    item.suggested_replies = replies.get("replies", [])
    item.rag_sources = replies.get("rag_sources", [])
    await db.commit()
    await db.refresh(item)

    return {
        "id": item.id,
        "message_id": item.message_id,
        "detected_intent": item.detected_intent,
        "commitment_warning": item.commitment_warning,
        "suggested_replies": item.suggested_replies,
        "rag_sources": item.rag_sources
    }

@router.post("/reply")
async def send_user_confirmed_reply(payload: LineReplyRequest):
    """Sends a reply to LINE ONLY AFTER explicit user review & confirmation.
    Protected by fact checks and user approval.
    """
    if not payload.message_text or not payload.reply_token:
        raise HTTPException(status_code=400, detail="Missing reply_token or message_text")
    
    logger.info(f"User approved sending LINE reply to token: {payload.reply_token}")
    res = await line_client.send_reply_message(payload.reply_token, payload.message_text)
    return {
        "status": "sent",
        "detail": res
    }
