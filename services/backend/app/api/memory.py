import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import TranslationMemory, Project
from app.providers.registry import provider_registry
from app.schemas.schemas import TranslationMemoryCreate, TranslationMemoryResponse

router = APIRouter(prefix="/api/memory", tags=["Translation Memory"])

@router.get("", response_model=List[TranslationMemoryResponse])
async def list_memories(
    project_id: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(TranslationMemory)
    if project_id:
        query = query.where(or_(TranslationMemory.project_id == project_id, TranslationMemory.project_id == None))
    if search:
        search_pat = f"%{search}%"
        query = query.where(
            or_(
                TranslationMemory.source_text.ilike(search_pat),
                TranslationMemory.target_text.ilike(search_pat)
            )
        )

    query = query.order_by(TranslationMemory.created_at.desc()).limit(100)
    result = await db.execute(query)
    items = result.scalars().all()

    response = []
    for m in items:
        p_name = None
        if m.project_id:
            p_res = await db.execute(select(Project.name).where(Project.id == m.project_id))
            p_name = p_res.scalar_one_or_none()

        response.append(TranslationMemoryResponse(
            id=m.id,
            project_id=m.project_id,
            project_name=p_name,
            source_text=m.source_text,
            target_text=m.target_text,
            source_language=m.source_language,
            target_language=m.target_language,
            style=m.style,
            provider=m.provider,
            model=m.model,
            quality_signal=m.quality_signal,
            user_edited=m.user_edited,
            created_at=m.created_at
        ))
    return response

@router.post("", response_model=TranslationMemoryResponse)
async def create_memory(data: TranslationMemoryCreate, db: AsyncSession = Depends(get_db)):
    # Generate vector embedding for semantic search if Ollama available
    emb_vector_str = None
    ollama_prov = provider_registry.get_provider("ollama")
    if ollama_prov:
        emb = await ollama_prov.get_embedding(data.source_text)
        if emb:
            emb_vector_str = json.dumps(emb)

    item = TranslationMemory(
        project_id=data.project_id,
        source_text=data.source_text.strip(),
        target_text=data.target_text.strip(),
        source_language=data.source_language,
        target_language=data.target_language,
        style=data.style or "business",
        provider=data.provider,
        model=data.model,
        quality_signal=data.quality_signal,
        user_edited=data.user_edited,
        embedding_vector=emb_vector_str
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    p_name = None
    if item.project_id:
        p_res = await db.execute(select(Project.name).where(Project.id == item.project_id))
        p_name = p_res.scalar_one_or_none()

    return TranslationMemoryResponse(
        id=item.id,
        project_id=item.project_id,
        project_name=p_name,
        source_text=item.source_text,
        target_text=item.target_text,
        source_language=item.source_language,
        target_language=item.target_language,
        style=item.style,
        provider=item.provider,
        model=item.model,
        quality_signal=item.quality_signal,
        user_edited=item.user_edited,
        created_at=item.created_at
    )

@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TranslationMemory).where(TranslationMemory.id == memory_id))
    m = result.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Translation memory entry not found.")
    await db.delete(m)
    await db.commit()
    return {"message": "Memory entry deleted."}
