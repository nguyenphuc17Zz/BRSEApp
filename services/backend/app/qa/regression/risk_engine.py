"""Rule-based risk scoring with explicit reasons. No gut-feel AI risk.

Factors (§9): business importance, scope, historical bugs, dependency count,
coverage, automation, recent failures, complexity, user-facing impact.
"""
from typing import Any, Dict, List
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.models import WorkItem, ProjectRelationship
from app.qa.models import TestCase, RequirementCoverage
from app.qa.api_models import APITestConfig
from app.qa.ui_models import UIAutomationScript
from app.qa.execution_models import TestExecution

RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


async def assess_requirement_risk(
    db: AsyncSession, project_id: str, requirement_id: str,
    changed: bool = True,
) -> Dict[str, Any]:
    score = 0
    reasons: List[str] = []
    item = (await db.execute(select(WorkItem).where(WorkItem.id == requirement_id))).scalars().first()
    if not item:
        return {"risk": "MEDIUM", "score": 0, "reasons": ["Requirement not found — default MEDIUM"]}

    # business importance
    prio = (item.priority or "MEDIUM").upper()
    if prio == "CRITICAL":
        score += 3
        reasons.append("Priority CRITICAL (+3)")
    elif prio == "HIGH":
        score += 2
        reasons.append("Priority HIGH (+2)")

    # dependency count
    dep_out = (await db.execute(select(func.count(ProjectRelationship.id)).where(
        ProjectRelationship.project_id == project_id,
        ProjectRelationship.source_type == "requirement",
        ProjectRelationship.source_id == requirement_id,
        ProjectRelationship.relation_type.in_(["depends_on", "related_to", "implemented_by"]))
    )).scalar() or 0
    dep_in = (await db.execute(select(func.count(ProjectRelationship.id)).where(
        ProjectRelationship.project_id == project_id,
        ProjectRelationship.target_type == "requirement",
        ProjectRelationship.target_id == requirement_id,
        ProjectRelationship.relation_type.in_(["depends_on", "related_to"]))
    )).scalar() or 0
    deps = dep_out + dep_in
    if deps >= 5:
        score += 2
        reasons.append(f"{deps} dependencies (+2)")
    elif deps >= 2:
        score += 1
        reasons.append(f"{deps} dependencies (+1)")

    # historical bugs
    bug_ids = set((await db.execute(select(TestExecution.bug_work_item_id).where(
        TestExecution.requirement_id == requirement_id,
        TestExecution.bug_work_item_id.isnot(None)))).scalars().all())
    if len(bug_ids) >= 3:
        score += 2
        reasons.append(f"{len(bug_ids)} historical bugs (+2)")
    elif bug_ids:
        score += 1
        reasons.append(f"{len(bug_ids)} historical bug(s) (+1)")

    # recent failures (last 10 executions)
    recent = (await db.execute(select(TestExecution.status).where(
        TestExecution.requirement_id == requirement_id,
        TestExecution.status.in_(["PASS", "FAIL"])).order_by(
        desc(TestExecution.updated_at)).limit(10))).scalars().all()
    fails = sum(1 for s in recent if s == "FAIL")
    if fails >= 3:
        score += 2
        reasons.append(f"{fails}/10 recent failures (+2)")
    elif fails >= 1:
        score += 1
        reasons.append(f"{fails}/10 recent failures (+1)")

    # coverage / automation
    cases = (await db.execute(select(TestCase).where(
        TestCase.requirement_id == requirement_id,
        TestCase.status != "REJECTED"))).scalars().all()
    if not cases:
        score += 2
        reasons.append("No test cases (+2)")
    else:
        api_n = (await db.execute(select(func.count(APITestConfig.test_case_id)).where(
            APITestConfig.test_case_id.in_([c.id for c in cases])))).scalar() or 0
        ui_n = (await db.execute(select(func.count(UIAutomationScript.test_case_id)).where(
            UIAutomationScript.test_case_id.in_([c.id for c in cases])))).scalar() or 0
        if api_n + ui_n == 0:
            score += 1
            reasons.append("No automation coverage (+1)")
        cov = (await db.execute(select(RequirementCoverage).where(
            RequirementCoverage.requirement_id == requirement_id))).scalars().first()
        if cov and cov.status in ("NotCovered", "PartiallyCovered", "NotReviewed"):
            score += 1
            reasons.append(f"Design coverage {cov.status} (+1)")

    # change itself adds baseline
    if changed:
        score += 1
        reasons.append("Directly changed (+1)")

    # user-facing hint from title/description
    text = f"{item.title} {(item.description or '')}".lower()
    if any(k in text for k in ["screen", "画面", "ui", "button", "màn hình", "login", "search", "payment", "決済"]):
        score += 1
        reasons.append("User-facing area (+1)")

    if score >= 8:
        risk = "CRITICAL"
    elif score >= 5:
        risk = "HIGH"
    elif score >= 3:
        risk = "MEDIUM"
    else:
        risk = "LOW"
    return {"risk": risk, "score": score, "reasons": reasons}


def max_risk(risks: List[str]) -> str:
    best = "LOW"
    for r in risks:
        if RISK_ORDER.get(r, 0) > RISK_ORDER.get(best, 0):
            best = r
    return best
