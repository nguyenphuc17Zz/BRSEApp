import json
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import mask_api_key, decrypt_credential
from app.db.models import (
    Project, GlossaryTerm, TranslationMemory, TranslationResult,
    TranslationCorrection, ProviderConfig
)
from app.schemas.schemas import DashboardStats, ProjectResponse, GlossaryTermResponse, ProviderResponse, CorrectionResponse

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(project_id: str = None, db: AsyncSession = Depends(get_db)):
    # 1. Total counts
    total_projects = (await db.execute(select(func.count()).select_from(Project))).scalar() or 0
    total_glossary = (await db.execute(select(func.count()).select_from(GlossaryTerm))).scalar() or 0
    total_tm = (await db.execute(select(func.count()).select_from(TranslationMemory))).scalar() or 0
    total_translations = (await db.execute(select(func.count()).select_from(TranslationResult))).scalar() or 0

    # 2. Current active project
    current_proj_resp = None
    if project_id:
        p = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    else:
        p = (await db.execute(select(Project).order_by(Project.updated_at.desc()))).scalars().first()

    if p:
        current_proj_resp = ProjectResponse(
            id=p.id,
            name=p.name,
            code=p.code,
            description=p.description,
            client_name=p.client_name,
            source_language=p.source_language,
            target_language=p.target_language,
            default_style=p.default_style,
            is_active=p.is_active,
            created_at=p.created_at
        )

    # 3. Recent translations
    recent_q = select(TranslationResult).order_by(TranslationResult.created_at.desc()).limit(5)
    recent_res = (await db.execute(recent_q)).scalars().all()
    recent_translations = [
        {
            "id": r.id,
            "source_text": r.source_text[:60] + ("..." if len(r.source_text) > 60 else ""),
            "selected_translation": r.selected_translation[:60] + ("..." if len(r.selected_translation) > 60 else ""),
            "provider": r.provider,
            "model": r.model,
            "latency_ms": r.latency_ms,
            "created_at": r.created_at.isoformat()
        } for r in recent_res
    ]

    # 4. Top Glossary Terms
    top_terms_res = (await db.execute(select(GlossaryTerm).order_by(GlossaryTerm.created_at.desc()).limit(6))).scalars().all()
    top_glossary = [
        GlossaryTermResponse(
            id=t.id,
            project_id=t.project_id,
            scope=t.scope,
            source_term=t.source_term,
            target_term=t.target_term,
            source_language=t.source_language,
            target_language=t.target_language,
            definition=t.definition,
            category=t.category,
            notes=t.notes,
            priority=t.priority,
            is_active=t.is_active,
            created_at=t.created_at
        ) for t in top_terms_res
    ]

    # 5. Provider Status
    prov_res = (await db.execute(select(ProviderConfig).order_by(ProviderConfig.priority.asc()))).scalars().all()
    providers_status = [
        ProviderResponse(
            id=c.id,
            name=c.name,
            display_name=c.display_name,
            api_key_masked=mask_api_key(decrypt_credential(c.api_key_encrypted) if c.api_key_encrypted else None),
            base_url=c.base_url,
            default_model=c.default_model,
            available_models=json.loads(c.available_models_json or "[]"),
            priority=c.priority,
            is_enabled=c.is_enabled,
            is_healthy=c.is_healthy,
            health_message=c.health_message,
            last_checked_at=c.last_checked_at
        ) for c in prov_res
    ]

    # 6. Recent Corrections
    corr_res = (await db.execute(select(TranslationCorrection).order_by(TranslationCorrection.created_at.desc()).limit(5))).scalars().all()
    recent_corrections = [
        CorrectionResponse(
            id=c.id,
            project_id=c.project_id,
            source_text=c.source_text,
            original_translation=c.original_translation,
            corrected_translation=c.corrected_translation,
            language_pair=c.language_pair,
            context_note=c.context_note,
            apply_scope=c.apply_scope,
            created_at=c.created_at
        ) for c in corr_res
    ]

    return DashboardStats(
        current_project=current_proj_resp,
        total_projects=total_projects,
        total_glossary_terms=total_glossary,
        total_tm_entries=total_tm,
        total_translations=total_translations,
        recent_translations=recent_translations,
        top_glossary_terms=top_glossary,
        providers_status=providers_status,
        recent_corrections=recent_corrections
    )
