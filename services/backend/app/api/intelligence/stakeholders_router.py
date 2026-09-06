import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import logger
from app.intelligence.models import ProjectStakeholder
from app.db.models import Project

router = APIRouter(prefix="/api/intelligence/stakeholders", tags=["Project Stakeholders & Communicators"])

class StakeholderCreateRequest(BaseModel):
    project_id: str
    name: str
    role: Optional[str] = "Client PM"
    organization: Optional[str] = "Khách hàng"
    platform: Optional[str] = "all"
    notes: Optional[str] = None

class StakeholderUpdateRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    organization: Optional[str] = None
    platform: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None

MOCK_STAKEHOLDER_NAMES = [
    "Suzuki-san", "Tanaka-san", "Yamada-san", "An (BrSE)", "Huy (Dev Lead)", "Test Stakeholder"
]

@router.post("/clean-mock")
async def clean_mock_stakeholders(
    project_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Permanently deletes any legacy mock/starter stakeholders from the database."""
    stmt = delete(ProjectStakeholder).where(ProjectStakeholder.name.in_(MOCK_STAKEHOLDER_NAMES))
    if project_id and project_id not in ("all", "default-project"):
        stmt = stmt.where(ProjectStakeholder.project_id == project_id)
    res = await db.execute(stmt)
    await db.commit()
    logger.info(f"Cleaned {res.rowcount} mock stakeholders from database.")
    return {"message": "Mock stakeholders cleaned successfully", "deleted_count": res.rowcount}

@router.get("")
async def list_stakeholders(
    project_id: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    """Lists stakeholders / speakers for a specific project.
    Zero mock data auto-seeding: only returns genuine project stakeholders.
    """
    effective_pid = project_id if (project_id and project_id not in ("all", "default-project", "")) else None

    stmt = select(ProjectStakeholder)
    if effective_pid:
        stmt = stmt.where(ProjectStakeholder.project_id == effective_pid)
    if not include_inactive:
        stmt = stmt.where(ProjectStakeholder.is_active == True)
    
    stmt = stmt.order_by(ProjectStakeholder.created_at.asc())
    records = (await db.execute(stmt)).scalars().all()

    return [
        {
            "id": r.id,
            "project_id": r.project_id,
            "name": r.name,
            "role": r.role,
            "organization": r.organization,
            "platform": r.platform,
            "notes": r.notes,
            "is_active": r.is_active,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in records
    ]

@router.post("")
async def create_stakeholder(
    payload: StakeholderCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Creates a new project stakeholder / speaker."""
    if not payload.name or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Tên người nhắn không được để trống.")

    if not payload.project_id or not payload.project_id.strip():
        raise HTTPException(status_code=400, detail="Project ID không hợp lệ.")

    # Check project exists
    p_check = await db.get(Project, payload.project_id)
    if not p_check:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy dự án với ID '{payload.project_id}'.")

    item = ProjectStakeholder(
        project_id=payload.project_id,
        name=payload.name.strip(),
        role=(payload.role or "Client PM").strip(),
        organization=(payload.organization or "Khách hàng").strip(),
        platform=(payload.platform or "all").strip(),
        notes=payload.notes.strip() if payload.notes else None,
        is_active=True
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    return {
        "id": item.id,
        "project_id": item.project_id,
        "name": item.name,
        "role": item.role,
        "organization": item.organization,
        "platform": item.platform,
        "notes": item.notes,
        "is_active": item.is_active,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }

@router.put("/{stakeholder_id}")
async def update_stakeholder(
    stakeholder_id: str,
    payload: StakeholderUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Updates an existing project stakeholder."""
    item = await db.get(ProjectStakeholder, stakeholder_id)
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy người nhắn.")

    if payload.name is not None:
        if not payload.name.strip():
            raise HTTPException(status_code=400, detail="Tên người nhắn không được để trống.")
        item.name = payload.name.strip()

    if payload.role is not None:
        item.role = payload.role.strip()

    if payload.organization is not None:
        item.organization = payload.organization.strip()

    if payload.platform is not None:
        item.platform = payload.platform.strip()

    if payload.notes is not None:
        item.notes = payload.notes.strip() if payload.notes else None

    if payload.is_active is not None:
        item.is_active = payload.is_active

    item.updated_at = datetime.datetime.utcnow()
    await db.commit()
    await db.refresh(item)

    return {
        "id": item.id,
        "project_id": item.project_id,
        "name": item.name,
        "role": item.role,
        "organization": item.organization,
        "platform": item.platform,
        "notes": item.notes,
        "is_active": item.is_active,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }

@router.delete("/{stakeholder_id}")
async def delete_stakeholder(
    stakeholder_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Permanently deletes a stakeholder from a project."""
    item = await db.get(ProjectStakeholder, stakeholder_id)
    if not item:
        raise HTTPException(status_code=404, detail="Không tìm thấy người nhắn.")

    await db.delete(item)
    await db.commit()
    return {"success": True, "id": stakeholder_id, "message": "Đã xóa người nhắn thành công."}
