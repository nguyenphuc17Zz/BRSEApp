import datetime
import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import encrypt_credential, decrypt_credential
from app.integrations.models import IntegrationAccount, SlackChannelMapping, IntegrationAuditLog
from app.integrations.slack.client import SlackClient
from app.integrations.slack.context import SlackContextRetriever
from app.integrations.slack.analyzer import SlackMessageAnalyzer
from app.integrations.slack.reply import SlackReplyGenerator
from app.engine.pipeline import translation_pipeline
from app.schemas.schemas import TranslationRequest

router = APIRouter(prefix="/slack", tags=["Slack Integration"])

class SlackConnectRequest(BaseModel):
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    auth_code: Optional[str] = None
    bot_token: Optional[str] = None
    is_mock: bool = False
    workspace_name: str = "Example Corp Slack"

class SlackTranslateMessageRequest(BaseModel):
    channel_id: str
    channel_name: str
    message_ts: str
    message_text: str
    thread_ts: Optional[str] = None
    project_id: Optional[str] = None
    target_language: str = "vi"
    provider: str = "gemini"
    model: Optional[str] = None

class SlackGenerateReplyRequest(BaseModel):
    message_text: str
    thread_ts: Optional[str] = None
    channel_id: Optional[str] = None
    project_id: Optional[str] = None
    provider: str = "gemini"
    model: Optional[str] = None

class ChannelMappingCreate(BaseModel):
    channel_id: str
    channel_name: str
    project_id: Optional[str] = None
    auto_translate: bool = False
    min_priority_score: int = 60

@router.post("/connect")
async def connect_slack(req: SlackConnectRequest, db: AsyncSession = Depends(get_db)):
    """Connects Slack Workspace (Live OAuth / Token or Sandbox Mode)."""
    existing = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "slack"))).scalars().all()
    for acc in existing:
        await db.delete(acc)

    if req.is_mock or (not req.auth_code and not req.bot_token):
        account = IntegrationAccount(
            provider="slack",
            account_name="Slack Integration",
            workspace_name=req.workspace_name,
            workspace_id="T01MOCKWS",
            encrypted_access_token=encrypt_credential("mock_slack_bot_token"),
            scopes_json=json.dumps(["channels:read", "channels:history", "groups:history", "im:history", "users:read"]),
            is_active=True,
            is_mock=True,
            last_sync_at=datetime.datetime.utcnow()
        )
    else:
        token_str = req.bot_token
        if req.auth_code and req.client_id and req.client_secret:
            tokens = await SlackClient.exchange_code(
                code=req.auth_code,
                client_id=req.client_id,
                client_secret=req.client_secret,
                redirect_uri="http://127.0.0.1:8000/api/integrations/slack/callback"
            )
            token_str = tokens.get("access_token", "")

        account = IntegrationAccount(
            provider="slack",
            account_name="Slack Integration",
            workspace_name=req.workspace_name,
            workspace_id="T01LIVEWS",
            encrypted_access_token=encrypt_credential(token_str or "live_token"),
            scopes_json=json.dumps(["channels:read", "channels:history"]),
            is_active=True,
            is_mock=False,
            last_sync_at=datetime.datetime.utcnow()
        )

    db.add(account)
    await db.commit()
    await db.refresh(account)

    return {
        "status": "connected",
        "account_id": account.id,
        "workspace_name": account.workspace_name,
        "is_mock": account.is_mock
    }

@router.post("/disconnect")
async def disconnect_slack(db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "slack"))).scalars().all()
    for acc in existing:
        await db.delete(acc)
    await db.commit()
    return {"status": "disconnected"}

@router.get("/channels")
async def list_slack_channels(db: AsyncSession = Depends(get_db)):
    acc = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "slack", IntegrationAccount.is_active == True))).scalars().first()
    if not acc:
        raise HTTPException(status_code=400, detail="Slack is not connected.")

    token = decrypt_credential(acc.encrypted_access_token)
    channels = await SlackClient.list_channels(token, is_mock=acc.is_mock)
    return {"channels": channels}

@router.get("/channels/{channel_id}/messages")
async def get_channel_messages(channel_id: str, db: AsyncSession = Depends(get_db)):
    acc = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "slack", IntegrationAccount.is_active == True))).scalars().first()
    if not acc:
        raise HTTPException(status_code=400, detail="Slack is not connected.")

    token = decrypt_credential(acc.encrypted_access_token)
    raw_msgs = await SlackClient.get_channel_history(token, channel_id, is_mock=acc.is_mock)

    # Attach Smart Message Analysis & Priority Scores
    enriched = []
    for m in raw_msgs:
        analysis = SlackMessageAnalyzer.analyze_message(m.get("text", ""))
        enriched.append({
            **m,
            "analysis": analysis
        })

    return {"messages": enriched}

@router.post("/messages/translate")
async def translate_slack_message(
    req: SlackTranslateMessageRequest,
    db: AsyncSession = Depends(get_db)
):
    """Translates a Slack message with full thread context retrieval."""
    acc = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "slack", IntegrationAccount.is_active == True))).scalars().first()
    if not acc:
        raise HTTPException(status_code=400, detail="Slack is not connected.")

    token = decrypt_credential(acc.encrypted_access_token)

    # 1. Retrieve Thread Context
    thread_ctx = await SlackContextRetriever.build_message_context(
        token=token,
        channel_id=req.channel_id,
        channel_name=req.channel_name,
        message_ts=req.message_ts,
        thread_ts=req.thread_ts,
        is_mock=acc.is_mock
    )

    # 2. Check channel to project mapping if project_id not provided
    project_id = req.project_id
    if not project_id:
        mapping = (await db.execute(select(SlackChannelMapping).where(SlackChannelMapping.channel_id == req.channel_id))).scalar_one_or_none()
        if mapping:
            project_id = mapping.project_id

    # 3. Translate through core pipeline
    context_lines = [f"{m['sender']}: {m['text']}" for m in thread_ctx["messages"] if not m.get("is_current")]
    trans_res = await translation_pipeline.execute(
        db,
        TranslationRequest(
            source_text=req.message_text,
            source_language="ja",
            target_language=req.target_language,
            project_id=project_id,
            conversation_context=context_lines[-3:] if context_lines else None,
            preferred_provider=req.provider,
            force_model=req.model
        )
    )

    # Audit
    db.add(IntegrationAuditLog(
        integration="slack",
        operation="translate_message",
        project_id=project_id,
        source_id=f"{req.channel_id}:{req.message_ts}",
        provider=req.provider,
        model=req.model or "default",
        status="success"
    ))
    await db.commit()

    return {
        "translation": trans_res.translations[0].text,
        "candidate_translations": trans_res.translations,
        "thread_context": thread_ctx,
        "used_glossary": trans_res.used_glossary,
        "used_memory": trans_res.used_memory,
        "qa_warnings": trans_res.qa_warnings,
        "detected_terms": trans_res.detected_terms
    }

@router.post("/messages/reply")
async def generate_slack_reply(
    req: SlackGenerateReplyRequest,
    db: AsyncSession = Depends(get_db)
):
    """Generates 4 tailored Japanese replies. Never sends automatically."""
    acc = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "slack", IntegrationAccount.is_active == True))).scalars().first()
    token = decrypt_credential(acc.encrypted_access_token) if acc else "mock"

    thread_msgs = []
    if req.channel_id and req.thread_ts:
        thread_ctx = await SlackContextRetriever.build_message_context(
            token=token,
            channel_id=req.channel_id,
            channel_name="",
            message_ts=req.thread_ts,
            thread_ts=req.thread_ts,
            is_mock=acc.is_mock if acc else True
        )
        thread_msgs = thread_ctx.get("messages", [])

    replies = await SlackReplyGenerator.generate_replies(
        current_message=req.message_text,
        thread_context=thread_msgs,
        provider_name=req.provider,
        model=req.model
    )

    return {
        "incoming_message": req.message_text,
        "reply_options": replies,
        "status": "draft",
        "notice": "Replies are drafts only. AI never sends automatically."
    }

@router.get("/mappings")
async def get_channel_mappings(db: AsyncSession = Depends(get_db)):
    mappings = (await db.execute(select(SlackChannelMapping))).scalars().all()
    return {"mappings": mappings}

@router.post("/mappings")
async def create_channel_mapping(req: ChannelMappingCreate, db: AsyncSession = Depends(get_db)):
    acc = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "slack", IntegrationAccount.is_active == True))).scalars().first()
    if not acc:
        raise HTTPException(status_code=400, detail="Slack is not connected.")

    # Check if exists
    mapping = (await db.execute(select(SlackChannelMapping).where(SlackChannelMapping.channel_id == req.channel_id))).scalar_one_or_none()
    if mapping:
        mapping.project_id = req.project_id
        mapping.auto_translate = req.auto_translate
        mapping.min_priority_score = req.min_priority_score
    else:
        mapping = SlackChannelMapping(
            account_id=acc.id,
            channel_id=req.channel_id,
            channel_name=req.channel_name,
            project_id=req.project_id,
            auto_translate=req.auto_translate,
            min_priority_score=req.min_priority_score
        )
        db.add(mapping)

    await db.commit()
    await db.refresh(mapping)
    return {"mapping": mapping}
