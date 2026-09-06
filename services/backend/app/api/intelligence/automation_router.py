from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.intelligence.models import AutomationRule, AutomationRunLog
from app.intelligence.automation.policy_engine import policy_engine

router = APIRouter(prefix="/api/automation", tags=["Automation Policy"])

class AutomationRuleCreate(BaseModel):
    project_id: Optional[str] = None
    name: str
    event_trigger: str # message_received, requirement_extracted, deadline_detected, bug_detected
    condition_json: str = "{}"
    action_type: str # draft_reply_suggestion, create_proposed_work_item, create_deadline_work_item
    is_active: bool = True

class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    event_trigger: Optional[str] = None
    condition_json: Optional[str] = None
    action_type: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("/rules")
async def list_rules(project_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """Lists automation policy rules."""
    await policy_engine.ensure_default_rules(db, project_id)
    stmt = select(AutomationRule).order_by(AutomationRule.created_at.desc())
    if project_id:
        stmt = stmt.where((AutomationRule.project_id == project_id) | (AutomationRule.project_id == None))
    res = await db.execute(stmt)
    rules = res.scalars().all()
    return rules

@router.post("/rules")
async def create_rule(payload: AutomationRuleCreate, db: AsyncSession = Depends(get_db)):
    """Creates a new automation policy rule."""
    rule = AutomationRule(
        project_id=payload.project_id,
        name=payload.name,
        event_trigger=payload.event_trigger,
        condition_json=payload.condition_json,
        action_type=payload.action_type,
        is_active=payload.is_active
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule

@router.patch("/rules/{rule_id}")
async def update_rule(rule_id: str, payload: AutomationRuleUpdate, db: AsyncSession = Depends(get_db)):
    """Updates an automation rule."""
    stmt = select(AutomationRule).where(AutomationRule.id == rule_id)
    res = await db.execute(stmt)
    rule = res.scalars().first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    if payload.name is not None:
        rule.name = payload.name
    if payload.event_trigger is not None:
        rule.event_trigger = payload.event_trigger
    if payload.condition_json is not None:
        rule.condition_json = payload.condition_json
    if payload.action_type is not None:
        rule.action_type = payload.action_type
    if payload.is_active is not None:
        rule.is_active = payload.is_active
    await db.commit()
    await db.refresh(rule)
    return rule

@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    """Deletes an automation rule."""
    stmt = select(AutomationRule).where(AutomationRule.id == rule_id)
    res = await db.execute(stmt)
    rule = res.scalars().first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    await db.commit()
    return {"status": "deleted", "id": rule_id}

@router.get("/logs")
async def list_audit_logs(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Lists audit logs of all automated trigger runs and draft proposals."""
    stmt = select(AutomationRunLog).order_by(desc(AutomationRunLog.created_at)).limit(limit)
    res = await db.execute(stmt)
    logs = res.scalars().all()
    return logs
