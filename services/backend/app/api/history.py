import json
from typing import List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import TranslationResult, TranslationCorrection, TranslationMemory, Project
from app.schemas.schemas import CorrectionCreate, CorrectionResponse

router = APIRouter(prefix="/api/history", tags=["History & Corrections"])

@router.get("")
async def list_history(
    project_id: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    query = select(TranslationResult)
    if project_id:
        query = query.where(TranslationResult.project_id == project_id)
    if search:
        search_pat = f"%{search}%"
        query = query.where(
            or_(
                TranslationResult.source_text.ilike(search_pat),
                TranslationResult.selected_translation.ilike(search_pat)
            )
        )

    query = query.order_by(TranslationResult.created_at.desc()).limit(limit)
    res = await db.execute(query)
    results = res.scalars().all()

    items = []
    for r in results:
        p_name = None
        if r.project_id:
            p_res = await db.execute(select(Project.name).where(Project.id == r.project_id))
            p_name = p_res.scalar_one_or_none()

        items.append({
            "id": r.id,
            "session_id": r.session_id,
            "project_id": r.project_id,
            "project_name": p_name,
            "source_text": r.source_text,
            "selected_translation": r.selected_translation,
            "candidate_translations": json.loads(r.candidate_translations_json or "[]"),
            "source_language": r.source_language,
            "target_language": r.target_language,
            "style": r.style,
            "provider": r.provider,
            "model": r.model,
            "latency_ms": r.latency_ms,
            "ambiguity_detected": r.ambiguity_detected,
            "ambiguity_reason": r.ambiguity_reason,
            "qa_warnings": json.loads(r.qa_warnings_json or "[]"),
            "created_at": r.created_at.isoformat()
        })
    return items

@router.get("/{result_id}")
async def get_history_detail(result_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(TranslationResult).where(TranslationResult.id == result_id))
    r = res.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Translation result not found.")

    p_name = None
    if r.project_id:
        p_res = await db.execute(select(Project.name).where(Project.id == r.project_id))
        p_name = p_res.scalar_one_or_none()

    return {
        "id": r.id,
        "session_id": r.session_id,
        "project_id": r.project_id,
        "project_name": p_name,
        "source_text": r.source_text,
        "selected_translation": r.selected_translation,
        "candidate_translations": json.loads(r.candidate_translations_json or "[]"),
        "source_language": r.source_language,
        "target_language": r.target_language,
        "style": r.style,
        "provider": r.provider,
        "model": r.model,
        "latency_ms": r.latency_ms,
        "ambiguity_detected": r.ambiguity_detected,
        "ambiguity_reason": r.ambiguity_reason,
        "qa_warnings": json.loads(r.qa_warnings_json or "[]"),
        "used_glossary": json.loads(r.used_glossary_json or "[]"),
        "used_memory": json.loads(r.used_memory_json or "[]"),
        "created_at": r.created_at.isoformat()
    }

@router.delete("/{result_id}")
async def delete_history(result_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(TranslationResult).where(TranslationResult.id == result_id))
    r = res.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Translation not found.")
    await db.delete(r)
    await db.commit()
    return {"message": "Translation history item deleted."}

# --- User Corrections (Learning Engine) ---
@router.post("/corrections", response_model=CorrectionResponse)
async def record_user_correction(data: CorrectionCreate, db: AsyncSession = Depends(get_db)):
    """Stores user correction so future translations for this project or globally will learn and adapt."""
    correction = TranslationCorrection(
        project_id=data.project_id,
        source_text=data.source_text.strip(),
        original_translation=data.original_translation.strip(),
        corrected_translation=data.corrected_translation.strip(),
        language_pair=data.language_pair,
        context_note=data.context_note,
        apply_scope=data.apply_scope
    )
    db.add(correction)

    # If save_to_tm is true, automatically add high-quality entry to Translation Memory!
    if data.save_to_tm:
        tm_item = TranslationMemory(
            project_id=data.project_id,
            source_text=data.source_text.strip(),
            target_text=data.corrected_translation.strip(),
            source_language=data.language_pair.split("-")[0] if "-" in data.language_pair else "ja",
            target_language=data.language_pair.split("-")[1] if "-" in data.language_pair else "vi",
            style="user_verified",
            provider="human_correction",
            model="user",
            quality_signal=1.0,
            user_edited=True
        )
        db.add(tm_item)

    await db.commit()
    await db.refresh(correction)

    return CorrectionResponse(
        id=correction.id,
        project_id=correction.project_id,
        source_text=correction.source_text,
        original_translation=correction.original_translation,
        corrected_translation=correction.corrected_translation,
        language_pair=correction.language_pair,
        context_note=correction.context_note,
        apply_scope=correction.apply_scope,
        created_at=correction.created_at
    )

@router.get("/corrections/list", response_model=List[CorrectionResponse])
async def list_corrections(project_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    query = select(TranslationCorrection)
    if project_id:
        query = query.where(or_(TranslationCorrection.project_id == project_id, TranslationCorrection.apply_scope == "global"))
    query = query.order_by(TranslationCorrection.created_at.desc()).limit(50)
    res = await db.execute(query)
    return res.scalars().all()
