from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.logging import logger
from app.db.models import Project, ProjectInstruction, GlossaryTerm, TranslationMemory
from app.documents.models import DocumentFile, DocumentJob
from app.intelligence.models import (
    MeetingRecord, WorkItem, WorkItemEvidence, ProjectStakeholder, ProjectDocumentChunk
)
from app.schemas.schemas import (
    ProjectCreate, ProjectUpdate, ProjectResponse,
    ProjectInstructionCreate, ProjectInstructionResponse
)

router = APIRouter(prefix="/api/projects", tags=["Projects"])

@router.get("", response_model=List[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    """Lists all active projects with counts of instructions, glossaries, and TMs."""
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    projects = result.scalars().all()

    response = []
    for p in projects:
        inst_cnt = (await db.execute(select(func.count()).select_from(ProjectInstruction).where(ProjectInstruction.project_id == p.id))).scalar() or 0
        glo_cnt = (await db.execute(select(func.count()).select_from(GlossaryTerm).where(GlossaryTerm.project_id == p.id))).scalar() or 0
        tm_cnt = (await db.execute(select(func.count()).select_from(TranslationMemory).where(TranslationMemory.project_id == p.id))).scalar() or 0

        response.append(ProjectResponse(
            id=p.id,
            name=p.name,
            code=p.code,
            description=p.description,
            client_name=p.client_name,
            source_language=p.source_language,
            target_language=p.target_language,
            default_style=p.default_style,
            is_active=p.is_active,
            created_at=p.created_at,
            instructions_count=inst_cnt,
            glossary_count=glo_cnt,
            tm_count=tm_cnt
        ))
    return response

@router.post("", response_model=ProjectResponse)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db)):
    """Creates a new project and initial instructions."""
    existing = await db.execute(select(Project).where(Project.code == data.code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Project with code '{data.code}' already exists.")

    project = Project(
        name=data.name,
        code=data.code,
        description=data.description,
        client_name=data.client_name,
        source_language=data.source_language,
        target_language=data.target_language,
        default_style=data.default_style
    )
    db.add(project)
    await db.flush()

    if data.instructions:
        for idx, rule in enumerate(data.instructions):
            inst = ProjectInstruction(
                project_id=project.id,
                rule_text=rule,
                priority=10 - idx
            )
            db.add(inst)

    await db.commit()
    await db.refresh(project)

    return ProjectResponse(
        id=project.id,
        name=project.name,
        code=project.code,
        description=project.description,
        client_name=project.client_name,
        source_language=project.source_language,
        target_language=project.target_language,
        default_style=project.default_style,
        is_active=project.is_active,
        created_at=project.created_at,
        instructions_count=len(data.instructions) if data.instructions else 0,
        glossary_count=0,
        tm_count=0
    )

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found.")

    inst_cnt = (await db.execute(select(func.count()).select_from(ProjectInstruction).where(ProjectInstruction.project_id == p.id))).scalar() or 0
    glo_cnt = (await db.execute(select(func.count()).select_from(GlossaryTerm).where(GlossaryTerm.project_id == p.id))).scalar() or 0
    tm_cnt = (await db.execute(select(func.count()).select_from(TranslationMemory).where(TranslationMemory.project_id == p.id))).scalar() or 0

    return ProjectResponse(
        id=p.id,
        name=p.name,
        code=p.code,
        description=p.description,
        client_name=p.client_name,
        source_language=p.source_language,
        target_language=p.target_language,
        default_style=p.default_style,
        is_active=p.is_active,
        created_at=p.created_at,
        instructions_count=inst_cnt,
        glossary_count=glo_cnt,
        tm_count=tm_cnt
    )

@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: str, data: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found.")

    for k, v in data.dict(exclude_unset=True).items():
        setattr(p, k, v)

    await db.commit()
    await db.refresh(p)
    return await get_project(project_id, db)

@router.delete("/{project_id}")
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found.")

    # 1. Clean up all physical DocumentFiles and Job outputs on disk
    try:
        from app.documents.storage import WORKING_DIR
        doc_res = await db.execute(select(DocumentFile).where(DocumentFile.project_id == project_id))
        doc_files = doc_res.scalars().all()
        for df in doc_files:
            # Delete original file
            try:
                orig_p = Path(df.original_path)
                if orig_p.exists():
                    orig_p.unlink()
            except Exception:
                pass
            # Delete output files and working copies
            stmt_j = select(DocumentJob).where(DocumentJob.document_id == df.id)
            jobs = (await db.execute(stmt_j)).scalars().all()
            for j in jobs:
                if j.output_path:
                    try:
                        out_p = Path(j.output_path)
                        if out_p.exists():
                            out_p.unlink()
                    except Exception:
                        pass
                try:
                    for wp in WORKING_DIR.glob(f"job_{j.id}_working*"):
                        if wp.exists():
                            wp.unlink()
                except Exception:
                    pass
            await db.delete(df)
    except Exception as doc_err:
        logger.warning(f"Error cleaning project documents on disk: {doc_err}")

    # 2. Clean up Project Document RAG chunks and FTS5 table
    try:
        await db.execute(
            text("DELETE FROM fts_project_documents WHERE project_id = :pid"),
            {"pid": project_id}
        )
        await db.execute(
            delete(ProjectDocumentChunk).where(ProjectDocumentChunk.project_id == project_id)
        )
    except Exception as rag_err:
        logger.warning(f"Error cleaning RAG chunks: {rag_err}")

    # 3. Clean up Project Glossary & Translation Memory (and FTS tables)
    try:
        gloss_ids = (await db.execute(select(GlossaryTerm.id).where(GlossaryTerm.project_id == project_id))).scalars().all()
        for gid in gloss_ids:
            await db.execute(text("DELETE FROM fts_glossary WHERE term_id = :tid"), {"tid": gid})
        await db.execute(delete(GlossaryTerm).where(GlossaryTerm.project_id == project_id))

        tm_ids = (await db.execute(select(TranslationMemory.id).where(TranslationMemory.project_id == project_id))).scalars().all()
        for tmid in tm_ids:
            await db.execute(text("DELETE FROM fts_memory WHERE memory_id = :mid"), {"mid": tmid})
        await db.execute(delete(TranslationMemory).where(TranslationMemory.project_id == project_id))
    except Exception as tm_err:
        logger.warning(f"Error cleaning glossary/memory: {tm_err}")

    # 4. Clean up Intelligence items (WorkItemEvidence, WorkItem, MeetingRecord, Stakeholders)
    try:
        m_ids = (await db.execute(select(MeetingRecord.id).where(MeetingRecord.project_id == project_id))).scalars().all()
        w_ids = (await db.execute(select(WorkItem.id).where(WorkItem.project_id == project_id))).scalars().all()
        
        if m_ids:
            await db.execute(delete(WorkItemEvidence).where(WorkItemEvidence.source_id.in_(m_ids)))
        if w_ids:
            await db.execute(delete(WorkItemEvidence).where(WorkItemEvidence.work_item_id.in_(w_ids)))
            
        await db.execute(delete(WorkItem).where(WorkItem.project_id == project_id))
        await db.execute(delete(MeetingRecord).where(MeetingRecord.project_id == project_id))
        await db.execute(delete(ProjectStakeholder).where(ProjectStakeholder.project_id == project_id))
    except Exception as intel_err:
        logger.warning(f"Error cleaning intelligence records: {intel_err}")

    # 5. Delete project instructions & Project record
    await db.execute(delete(ProjectInstruction).where(ProjectInstruction.project_id == project_id))
    await db.delete(p)
    await db.commit()
    return {"message": "Project and all associated physical files, RAG chunks, and database records deleted successfully."}

@router.get("/{project_id}/instructions", response_model=List[ProjectInstructionResponse])
async def list_project_instructions(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ProjectInstruction)
        .where(ProjectInstruction.project_id == project_id)
        .order_by(ProjectInstruction.priority.desc())
    )
    return result.scalars().all()

@router.post("/{project_id}/instructions", response_model=ProjectInstructionResponse)
async def add_project_instruction(project_id: str, data: ProjectInstructionCreate, db: AsyncSession = Depends(get_db)):
    inst = ProjectInstruction(
        project_id=project_id,
        rule_text=data.rule_text,
        category=data.category,
        priority=data.priority
    )
    db.add(inst)
    await db.commit()
    await db.refresh(inst)
    return inst

@router.delete("/{project_id}/instructions/{instruction_id}")
async def delete_project_instruction(project_id: str, instruction_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ProjectInstruction).where(
            ProjectInstruction.id == instruction_id,
            ProjectInstruction.project_id == project_id
        )
    )
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(status_code=404, detail="Instruction not found.")
    await db.delete(inst)
    await db.commit()
    return {"message": "Instruction deleted."}
