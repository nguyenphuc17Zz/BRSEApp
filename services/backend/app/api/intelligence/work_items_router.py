import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.intelligence.models import WorkItem, WorkItemEvidence, ProjectRelationship

router = APIRouter(tags=["BrSE Work Items"])

class EvidenceResponse(BaseModel):
    id: str
    source_type: str
    source_id: str
    quote_text: str
    author: Optional[str] = None
    timestamp: Optional[str] = None
    confidence: float
    confirmation_status: str

    class Config:
        from_attributes = True

class WorkItemResponse(BaseModel):
    id: str
    project_id: str
    item_type: str
    title: str
    description: str
    details_json: str
    status: str
    priority: str
    assignee: Optional[str] = None
    deadline_date: Optional[str] = None
    confidence: float
    version: int
    is_conflict: bool
    conflict_notes: Optional[str] = None
    created_at: str
    updated_at: str
    evidence_items: List[EvidenceResponse] = []

    class Config:
        from_attributes = True

class WorkItemCreate(BaseModel):
    project_id: str
    item_type: str
    title: str
    description: str = ""
    details_json: str = "{}"
    status: str = "PROPOSED"
    priority: str = "MEDIUM"
    assignee: Optional[str] = None
    deadline_date: Optional[str] = None
    confidence: float = 0.90
    quote_text: Optional[str] = None
    source_type: str = "manual"
    source_id: str = "user_input"

class WorkItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee: Optional[str] = None
    deadline_date: Optional[str] = None
    details_json: Optional[str] = None
    is_conflict: Optional[bool] = None
    conflict_notes: Optional[str] = None

@router.get("/api/work-items", response_model=List[WorkItemResponse])
async def list_work_items(
    project_id: Optional[str] = None,
    item_type: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    is_conflict: Optional[bool] = None,
    db: AsyncSession = Depends(get_db)
):
    """Lists all work items with optional filtering."""
    stmt = select(WorkItem).options(selectinload(WorkItem.evidence_items)).order_by(desc(WorkItem.created_at))
    if project_id:
        stmt = stmt.where(WorkItem.project_id == project_id)
    if item_type:
        stmt = stmt.where(WorkItem.item_type == item_type.upper())
    if status:
        stmt = stmt.where(WorkItem.status == status.upper())
    if priority:
        stmt = stmt.where(WorkItem.priority == priority.upper())
    if is_conflict is not None:
        stmt = stmt.where(WorkItem.is_conflict == is_conflict)

    res = await db.execute(stmt)
    items = res.scalars().all()
    
    # Format for response
    out = []
    for item in items:
        out.append(WorkItemResponse(
            id=item.id,
            project_id=item.project_id,
            item_type=item.item_type,
            title=item.title,
            description=item.description,
            details_json=item.details_json,
            status=item.status,
            priority=item.priority,
            assignee=item.assignee,
            deadline_date=item.deadline_date,
            confidence=item.confidence,
            version=item.version,
            is_conflict=item.is_conflict,
            conflict_notes=item.conflict_notes,
            created_at=item.created_at.isoformat() if item.created_at else "",
            updated_at=item.updated_at.isoformat() if item.updated_at else "",
            evidence_items=[
                EvidenceResponse(
                    id=e.id,
                    source_type=e.source_type,
                    source_id=e.source_id,
                    quote_text=e.quote_text,
                    author=e.author,
                    timestamp=e.timestamp,
                    confidence=e.confidence,
                    confirmation_status=e.confirmation_status
                ) for e in item.evidence_items
            ]
        ))
    return out

@router.get("/api/work-items/{item_id}", response_model=WorkItemResponse)
async def get_work_item(item_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieves a single work item with all evidence citations."""
    stmt = select(WorkItem).options(selectinload(WorkItem.evidence_items)).where(WorkItem.id == item_id)
    res = await db.execute(stmt)
    item = res.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    
    return WorkItemResponse(
        id=item.id,
        project_id=item.project_id,
        item_type=item.item_type,
        title=item.title,
        description=item.description,
        details_json=item.details_json,
        status=item.status,
        priority=item.priority,
        assignee=item.assignee,
        deadline_date=item.deadline_date,
        confidence=item.confidence,
        version=item.version,
        is_conflict=item.is_conflict,
        conflict_notes=item.conflict_notes,
        created_at=item.created_at.isoformat() if item.created_at else "",
        updated_at=item.updated_at.isoformat() if item.updated_at else "",
        evidence_items=[
            EvidenceResponse(
                id=e.id,
                source_type=e.source_type,
                source_id=e.source_id,
                quote_text=e.quote_text,
                author=e.author,
                timestamp=e.timestamp,
                confidence=e.confidence,
                confirmation_status=e.confirmation_status
            ) for e in item.evidence_items
        ]
    )

@router.post("/api/work-items", response_model=WorkItemResponse)
async def create_work_item(payload: WorkItemCreate, db: AsyncSession = Depends(get_db)):
    """Creates a new work item with evidence."""
    item = WorkItem(
        project_id=payload.project_id,
        item_type=payload.item_type.upper(),
        title=payload.title,
        description=payload.description,
        details_json=payload.details_json,
        status=payload.status.upper(),
        priority=payload.priority.upper(),
        assignee=payload.assignee,
        deadline_date=payload.deadline_date,
        confidence=payload.confidence
    )
    db.add(item)
    await db.flush()

    if payload.quote_text:
        ev = WorkItemEvidence(
            work_item_id=item.id,
            source_type=payload.source_type,
            source_id=payload.source_id,
            quote_text=payload.quote_text,
            confirmation_status=payload.status.upper()
        )
        db.add(ev)
    
    await db.commit()
    await db.refresh(item)
    # Re-fetch with evidence
    return await get_work_item(item.id, db)

@router.patch("/api/work-items/{item_id}", response_model=WorkItemResponse)
async def update_work_item(item_id: str, payload: WorkItemUpdate, db: AsyncSession = Depends(get_db)):
    """Updates fields of an existing work item."""
    stmt = select(WorkItem).options(selectinload(WorkItem.evidence_items)).where(WorkItem.id == item_id)
    res = await db.execute(stmt)
    item = res.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")

    if payload.title is not None:
        item.title = payload.title
    if payload.description is not None:
        item.description = payload.description
    if payload.status is not None:
        item.status = payload.status.upper()
    if payload.priority is not None:
        item.priority = payload.priority.upper()
    if payload.assignee is not None:
        item.assignee = payload.assignee
    if payload.deadline_date is not None:
        item.deadline_date = payload.deadline_date
    if payload.details_json is not None:
        item.details_json = payload.details_json
    if payload.is_conflict is not None:
        item.is_conflict = payload.is_conflict
    if payload.conflict_notes is not None:
        item.conflict_notes = payload.conflict_notes

    await db.commit()
    return await get_work_item(item.id, db)

@router.post("/api/work-items/{item_id}/confirm", response_model=WorkItemResponse)
async def confirm_work_item(item_id: str, db: AsyncSession = Depends(get_db)):
    """Human-in-the-loop: Explicit user confirmation turns a proposed item into project knowledge."""
    stmt = select(WorkItem).options(selectinload(WorkItem.evidence_items)).where(WorkItem.id == item_id)
    res = await db.execute(stmt)
    item = res.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")

    item.status = "CONFIRMED"
    item.is_conflict = False
    for ev in item.evidence_items:
        ev.confirmation_status = "CONFIRMED"

    await db.commit()
    return await get_work_item(item.id, db)

@router.post("/api/work-items/{item_id}/reject", response_model=WorkItemResponse)
async def reject_work_item(item_id: str, db: AsyncSession = Depends(get_db)):
    """Human-in-the-loop: User rejects an AI-proposed work item."""
    stmt = select(WorkItem).options(selectinload(WorkItem.evidence_items)).where(WorkItem.id == item_id)
    res = await db.execute(stmt)
    item = res.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")

    item.status = "REJECTED"
    await db.commit()
    return await get_work_item(item.id, db)

@router.post("/api/work-items/{item_id}/reset", response_model=WorkItemResponse)
async def reset_work_item(item_id: str, db: AsyncSession = Depends(get_db)):
    """Human-in-the-loop: User resets a confirmed or rejected item back to PROPOSED/pending."""
    stmt = select(WorkItem).options(selectinload(WorkItem.evidence_items)).where(WorkItem.id == item_id)
    res = await db.execute(stmt)
    item = res.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")

    item.status = "PROPOSED"
    for ev in item.evidence_items:
        ev.confirmation_status = "PENDING"

    await db.commit()
    return await get_work_item(item.id, db)

@router.delete("/api/work-items/{item_id}")
async def delete_work_item(item_id: str, db: AsyncSession = Depends(get_db)):
    """Deletes a work item."""
    stmt = select(WorkItem).where(WorkItem.id == item_id)
    res = await db.execute(stmt)
    item = res.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    await db.delete(item)
    await db.commit()
    return {"status": "deleted", "id": item_id}

# Specific Project Views
@router.get("/api/projects/{project_id}/requirements")
async def get_project_requirements(project_id: str, db: AsyncSession = Depends(get_db)):
    return await list_work_items(project_id=project_id, item_type="REQUIREMENT", db=db)

@router.get("/api/projects/{project_id}/bugs")
async def get_project_bugs(project_id: str, db: AsyncSession = Depends(get_db)):
    return await list_work_items(project_id=project_id, item_type="BUG", db=db)

@router.get("/api/projects/{project_id}/decisions")
async def get_project_decisions(project_id: str, db: AsyncSession = Depends(get_db)):
    return await list_work_items(project_id=project_id, item_type="DECISION", db=db)

@router.get("/api/projects/{project_id}/todos")
async def get_project_todos(project_id: str, db: AsyncSession = Depends(get_db)):
    return await list_work_items(project_id=project_id, item_type="TODO", db=db)

@router.get("/api/projects/{project_id}/risks")
async def get_project_risks(project_id: str, db: AsyncSession = Depends(get_db)):
    return await list_work_items(project_id=project_id, item_type="RISK", db=db)

@router.get("/api/projects/{project_id}/questions")
async def get_project_questions(project_id: str, db: AsyncSession = Depends(get_db)):
    return await list_work_items(project_id=project_id, item_type="OPEN_QUESTION", db=db)

@router.get("/api/projects/{project_id}/timeline")
async def get_project_timeline(project_id: str, db: AsyncSession = Depends(get_db)):
    """Returns chronological timeline of all project milestones, decisions, and requirements."""
    stmt = select(WorkItem).options(selectinload(WorkItem.evidence_items)).where(
        WorkItem.project_id == project_id
    ).order_by(desc(WorkItem.created_at))
    res = await db.execute(stmt)
    items = res.scalars().all()
    
    events = []
    for item in items:
        events.append({
            "id": item.id,
            "type": item.item_type,
            "title": item.title,
            "status": item.status,
            "priority": item.priority,
            "date": item.created_at.strftime("%b %d, %Y %H:%M") if item.created_at else "",
            "evidence": [e.quote_text for e in item.evidence_items[:2]]
        })
    return {"project_id": project_id, "timeline": events}
