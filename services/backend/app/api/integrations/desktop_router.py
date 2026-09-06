from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import Project
from app.integrations.desktop.agent import desktop_agent
from app.integrations.desktop.app_detector import WindowsAppDetector
from app.integrations.desktop.profiles import DesktopProfileManager
from app.integrations.desktop.clipboard import ClipboardService
from app.integrations.slack.reply import SlackReplyGenerator
from app.engine.pipeline import translation_pipeline
from app.schemas.schemas import TranslationRequest

router = APIRouter(prefix="/desktop", tags=["Windows Desktop Integration"])

class DesktopConfigRequest(BaseModel):
    shortcuts: Dict[str, str]

class QuickTranslateRequest(BaseModel):
    text: Optional[str] = None
    target_language: str = "vi"
    project_id: Optional[str] = None
    style: Optional[str] = None
    provider: str = "gemini"
    model: Optional[str] = None

@router.get("/status")
async def get_desktop_status():
    return desktop_agent.get_status()

@router.post("/config")
async def update_desktop_config(req: DesktopConfigRequest):
    desktop_agent.update_shortcuts(req.shortcuts)
    return {"status": "updated", "shortcuts": desktop_agent.shortcuts}

@router.get("/active-window")
async def get_active_window(db: AsyncSession = Depends(get_db)):
    win_info = WindowsAppDetector.get_foreground_window_info()
    profile = DesktopProfileManager.get_profile_for_app(win_info.get("process_name", ""))

    projects = (await db.execute(select(Project))).scalars().all()
    matched_project = DesktopProfileManager.match_project_from_title(win_info.get("title", ""), projects)

    return {
        **win_info,
        "profile": profile,
        "matched_project": {
            "id": matched_project.id,
            "name": matched_project.name,
            "code": matched_project.code
        } if matched_project else None
    }

@router.post("/quick-translate")
async def quick_translate(req: QuickTranslateRequest, db: AsyncSession = Depends(get_db)):
    """Triggers instant quick translation for highlighted or clipboard text with app-aware profiling."""
    source_text = req.text
    if not source_text:
        source_text = ClipboardService.get_text()

    if not source_text.strip():
        return {
            "source_text": "",
            "translation": "No text detected in clipboard or selection.",
            "status": "empty"
        }

    # Inspect foreground window context
    win_info = WindowsAppDetector.get_foreground_window_info()
    profile = DesktopProfileManager.get_profile_for_app(win_info.get("process_name", ""))

    # Auto-match project if not explicitly chosen
    project_id = req.project_id
    if not project_id:
        projects = (await db.execute(select(Project))).scalars().all()
        matched = DesktopProfileManager.match_project_from_title(win_info.get("title", ""), projects)
        if matched:
            project_id = matched.id

    chosen_style = req.style or profile.get("style", "Auto")

    trans_res = await translation_pipeline.execute(
        db,
        TranslationRequest(
            source_text=source_text,
            source_language="ja",
            target_language=req.target_language,
            project_id=project_id,
            style=chosen_style,
            preferred_provider=req.provider,
            force_model=req.model
        )
    )

    return {
        "source_text": source_text,
        "translation": trans_res.translations[0].text,
        "candidate_translations": trans_res.translations,
        "active_app": win_info.get("process_name"),
        "window_title": win_info.get("title"),
        "applied_style": chosen_style,
        "qa_warnings": trans_res.qa_warnings,
        "used_glossary": trans_res.used_glossary,
        "used_memory": trans_res.used_memory
    }

@router.post("/quick-reply")
async def quick_reply(req: QuickTranslateRequest, db: AsyncSession = Depends(get_db)):
    source_text = req.text or ClipboardService.get_text()
    replies = await SlackReplyGenerator.generate_replies(
        current_message=source_text,
        provider_name=req.provider,
        model=req.model
    )
    return {
        "source_text": source_text,
        "reply_options": replies
    }
