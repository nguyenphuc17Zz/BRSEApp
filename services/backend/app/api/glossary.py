from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import GlossaryTerm, Project
from app.schemas.schemas import GlossaryTermCreate, GlossaryTermUpdate, GlossaryTermResponse

router = APIRouter(prefix="/api/glossary", tags=["Glossary"])

@router.get("", response_model=List[GlossaryTermResponse])
async def list_glossary(
    project_id: Optional[str] = None,
    scope: Optional[str] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Retrieves glossary terms filtered by project, scope, search keyword, or category."""
    query = select(GlossaryTerm).where(GlossaryTerm.is_active == True)

    if project_id == "global_only":
        query = query.where(GlossaryTerm.scope == "global")
    elif project_id and project_id != "all":
        query = query.where(GlossaryTerm.project_id == project_id)
    if scope:
        query = query.where(GlossaryTerm.scope == scope)
    if category:
        query = query.where(GlossaryTerm.category == category)
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            or_(
                GlossaryTerm.source_term.ilike(search_pattern),
                GlossaryTerm.target_term.ilike(search_pattern),
                GlossaryTerm.definition.ilike(search_pattern)
            )
        )

    query = query.order_by(GlossaryTerm.created_at.desc())
    result = await db.execute(query)
    terms = result.scalars().all()

    response = []
    for t in terms:
        project_name = None
        if t.project_id:
            p_res = await db.execute(select(Project.name).where(Project.id == t.project_id))
            project_name = p_res.scalar_one_or_none()

        response.append(GlossaryTermResponse(
            id=t.id,
            project_id=t.project_id,
            project_name=project_name,
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
        ))
    return response

@router.post("", response_model=GlossaryTermResponse)
async def create_glossary_term(data: GlossaryTermCreate, db: AsyncSession = Depends(get_db)):
    term = GlossaryTerm(
        project_id=data.project_id,
        scope=data.scope,
        source_term=data.source_term.strip(),
        target_term=data.target_term.strip(),
        source_language=data.source_language,
        target_language=data.target_language,
        definition=data.definition,
        category=data.category or "IT",
        notes=data.notes,
        priority=data.priority
    )
    db.add(term)
    await db.commit()
    await db.refresh(term)

    project_name = None
    if term.project_id:
        p_res = await db.execute(select(Project.name).where(Project.id == term.project_id))
        project_name = p_res.scalar_one_or_none()

    return GlossaryTermResponse(
        id=term.id,
        project_id=term.project_id,
        project_name=project_name,
        scope=term.scope,
        source_term=term.source_term,
        target_term=term.target_term,
        source_language=term.source_language,
        target_language=term.target_language,
        definition=term.definition,
        category=term.category,
        notes=term.notes,
        priority=term.priority,
        is_active=term.is_active,
        created_at=term.created_at
    )

@router.patch("/{term_id}", response_model=GlossaryTermResponse)
async def update_glossary_term(term_id: str, data: GlossaryTermUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GlossaryTerm).where(GlossaryTerm.id == term_id))
    term = result.scalar_one_or_none()
    if not term:
        raise HTTPException(status_code=404, detail="Glossary term not found.")

    for k, v in data.dict(exclude_unset=True).items():
        setattr(term, k, v)

    await db.commit()
    await db.refresh(term)

    project_name = None
    if term.project_id:
        p_res = await db.execute(select(Project.name).where(Project.id == term.project_id))
        project_name = p_res.scalar_one_or_none()

    return GlossaryTermResponse(
        id=term.id,
        project_id=term.project_id,
        project_name=project_name,
        scope=term.scope,
        source_term=term.source_term,
        target_term=term.target_term,
        source_language=term.source_language,
        target_language=term.target_language,
        definition=term.definition,
        category=term.category,
        notes=term.notes,
        priority=term.priority,
        is_active=term.is_active,
        created_at=term.created_at
    )

@router.delete("/{term_id}")
async def delete_glossary_term(term_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GlossaryTerm).where(GlossaryTerm.id == term_id))
    term = result.scalar_one_or_none()
    if not term:
        raise HTTPException(status_code=404, detail="Glossary term not found.")
    await db.delete(term)
    await db.commit()
    return {"message": "Term deleted successfully."}

@router.delete("/project/{project_id}")
async def delete_project_glossary(project_id: str, db: AsyncSession = Depends(get_db)):
    """Deletes all glossary terms belonging to a specific project."""
    stmt = delete(GlossaryTerm).where(GlossaryTerm.project_id == project_id)
    result = await db.execute(stmt)
    await db.commit()
    deleted_count = result.rowcount if hasattr(result, "rowcount") else 0
    return {
        "message": f"Successfully deleted {deleted_count} glossary terms for project {project_id}.",
        "deleted_count": deleted_count
    }
