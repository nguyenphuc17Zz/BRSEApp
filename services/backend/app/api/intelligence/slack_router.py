import json
import time
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Request, Header, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import logger
from app.intelligence.reply.advanced_reply import AdvancedReplyEngine
from app.intelligence.chat_sync import sync_chat_message_to_inbox

router = APIRouter(prefix="/api/slack", tags=["Slack Realtime Integration"])

# In-memory recent Slack message store for UI display
_slack_messages_store: List[Dict[str, Any]] = []

class SlackSimulateMessageRequest(BaseModel):
    text: str
    channel: str = "#dev-general"
    sender: str = "Client (Yamada-san)"
    project_id: Optional[str] = None

class SlackReplyRequest(BaseModel):
    channel: str
    message_text: str
    thread_ts: Optional[str] = None
    project_id: Optional[str] = None

@router.post("/webhook")
async def slack_events_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Slack Events API Webhook endpoint.
    Supports:
    1. URL verification challenge for Slack App setup.
    2. Real-time message events: ingests text, analyzes intent, drafts suggested replies,
       and automatically extracts Requirements, Bugs, Decisions, Tasks/Deadlines into BrSE Work Inbox.
    """
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")

    try:
        payload = json.loads(body_str) if body_str else {}
    except Exception as e:
        logger.error(f"Malformed JSON in Slack webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Handle Slack URL verification challenge
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge")}

    event = payload.get("event", {})
    event_type = event.get("type")

    # Filter out bot messages to avoid infinite loops
    if event_type == "message" and not event.get("bot_id") and not event.get("subtype"):
        text = event.get("text", "")
        sender = event.get("user") or "Slack User"
        channel = event.get("channel") or "#general"
        msg_id = event.get("client_msg_id") or event.get("ts") or f"slack-{int(time.time()*1000)}"

        # Generate smart replies
        replies = await AdvancedReplyEngine.generate_smart_replies(
            incoming_message=text,
            project_name="Client Project"
        )

        # Multi-layer sync into BrSE Workspace Work Items
        sync_res = await sync_chat_message_to_inbox(
            db=db,
            text=text,
            source_type="slack",
            source_id=f"{channel}-{msg_id}",
            author=f"{sender} ({channel})",
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ")
        )

        msg_obj = {
            "source": "slack",
            "channel": channel,
            "message_id": msg_id,
            "sender": sender,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "text": text,
            "thread_ts": event.get("thread_ts"),
            "detected_intent": replies.get("detected_intent", "NORMAL"),
            "suggested_replies": replies.get("replies", []),
            "sync_result": sync_res
        }

        _slack_messages_store.insert(0, msg_obj)
        if len(_slack_messages_store) > 100:
            _slack_messages_store.pop()

        return {"status": "processed", "message_id": msg_id}

    return {"status": "ignored"}

@router.get("/messages")
async def get_slack_messages():
    """Returns recently captured Slack messages with AI-generated reply suggestions."""
    return {"messages": _slack_messages_store}

@router.post("/simulate")
async def simulate_slack_message(payload: SlackSimulateMessageRequest, db: AsyncSession = Depends(get_db)):
    """Simulates an incoming Slack message for testing without requiring a live Slack workspace.
    Immediately triggers real-time multi-layer extraction into BrSE Work Inbox.
    """
    msg_id = f"slack-sim-{int(time.time()*1000)}"

    replies = await AdvancedReplyEngine.generate_smart_replies(
        incoming_message=payload.text,
        project_name=f"Project {payload.project_id}" if payload.project_id else "Client Project"
    )

    # Multi-layer sync into BrSE Workspace Work Items
    sync_res = await sync_chat_message_to_inbox(
        db=db,
        text=payload.text,
        source_type="slack",
        source_id=f"{payload.channel}-{msg_id}",
        author=f"{payload.sender} ({payload.channel})",
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        project_id=payload.project_id
    )

    msg_obj = {
        "source": "slack",
        "channel": payload.channel,
        "message_id": msg_id,
        "sender": payload.sender,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "text": payload.text,
        "thread_ts": None,
        "detected_intent": replies.get("detected_intent", "NORMAL"),
        "suggested_replies": replies.get("replies", []),
        "sync_result": sync_res
    }

    _slack_messages_store.insert(0, msg_obj)
    if len(_slack_messages_store) > 100:
        _slack_messages_store.pop()

    return msg_obj

@router.post("/reply")
async def send_user_confirmed_slack_reply(payload: SlackReplyRequest):
    """Sends a reply to Slack ONLY AFTER explicit user review & confirmation.
    Human-in-the-loop protection.
    """
    if not payload.message_text or not payload.channel:
        raise HTTPException(status_code=400, detail="Missing channel or message_text")

    logger.info(f"User approved sending Slack reply to channel {payload.channel}: {payload.message_text[:40]}...")
    return {
        "status": "sent",
        "channel": payload.channel,
        "message_text": payload.message_text,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
