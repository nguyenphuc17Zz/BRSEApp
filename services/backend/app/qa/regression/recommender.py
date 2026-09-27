"""Regression recommendation: evidence-backed candidates, tiers, dedupe, time-box.

Every candidate answers 'Why should this test run?' (§14) with source +
relationship + reason (§41). No black-box picks.
"""
import json
from typing import Any, Dict, List, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.qa.models import TestCase
from app.qa.api_models import APITestConfig
from app.qa.ui_models import UIAutomationScript
from app.qa.execution_models import TestExecution
from app.qa.regression import impact_graph as IG
from app.qa.regression import risk_engine as RK

# rough minutes per execution type for time-boxing
TYPE_MINUTES = {"MANUAL": 10, "API": 2, "WEB_UI": 5}


async def _case_type(db: AsyncSession, test_case_id: str) -> str:
    ui = (await db.execute(select(UIAutomationScript.test_case_id).where(
        UIAutomationScript.test_case_id == test_case_id))).scalars().first()
    if ui:
        return "WEB_UI"
    api = (await db.execute(select(APITestConfig.test_case_id).where(
        APITestConfig.test_case_id == test_case_id))).scalars().first()
    if api:
        return "API"
    return "MANUAL"


async def _failure_boost(db: AsyncSession, test_case_id: str) -> int:
    """Previous-failure intelligence (§16): failing history raises priority."""
    seq = (await db.execute(select(TestExecution.status).where(
        TestExecution.test_case_id == test_case_id,
        TestExecution.status.in_(["PASS", "FAIL"])).order_by(
        desc(TestExecution.updated_at)).limit(5))).scalars().all()
    fails = sum(1 for s in seq if s == "FAIL")
    if len(seq) >= 4 and fails >= 2:
        return 2  # High Regression Value
    if fails >= 1:
        return 1
    return 0


async def recommend_for_changes(
    db: AsyncSession, change_ids: List[str],
    preferred_provider: Optional[str] = None, model: Optional[str] = None,
) -> Dict[str, Any]:
    """Merges impact of multiple changes, dedupes cases, keeps all reasons (§37)."""
    merged: Dict[str, Dict[str, Any]] = {}
    risks: Dict[str, str] = {}
    confidences: Dict[str, str] = {}
    bugs: Dict[str, Dict[str, Any]] = {}
    paths: Dict[str, List[str]] = {}

    for cid in change_ids:
        impact = await IG.build_impact(db, cid, preferred_provider, model)
        from app.qa.regression_models import ChangeRecord as _CR
        _ch = (await db.execute(select(_CR).where(_CR.id == cid))).scalars().first()
        _pid = _ch.project_id if _ch else ""
        for c in impact["cases"]:
            tcid = c["id"]
            entry = merged.setdefault(tcid, {"reasons": [], "because": []})
            entry["reasons"].append(
                f"{c['level']} impact from {impact['change_code']}: "
                f"{' → '.join(c['path'])}")
            entry["because"].append(impact["change_code"])
            # confidence: High for Direct, Medium Indirect, Low Possible
            conf = {"Direct": "High", "Indirect": "Medium", "Possible": "Low"}.get(c["level"], "Low")
            order = {"Low": 0, "Medium": 1, "High": 2}
            if order[conf] > order.get(confidences.get(tcid, "Low"), 0):
                confidences[tcid] = conf
            else:
                confidences.setdefault(tcid, conf)
            paths.setdefault(tcid, []).append(" → ".join(c["path"]))
        for b in impact["bugs"]:
            bugs[b["id"]] = {"id": b["id"], "code": b["code"], "title": b["title"],
                             "label": "Historical Bug Regression",
                             "because": impact["change_code"]}
        # requirement-level risk for tiering
        for rid in impact["seed_requirements"]:
            r = await RK.assess_requirement_risk(db, _pid, rid)
            risks[rid] = r["risk"]
        # store project + risk detail per case requirement
        for c in impact["cases"]:
            tc = (await db.execute(select(TestCase).where(TestCase.id == c["id"]))).scalars().first()
            if tc and tc.requirement_id not in risks:
                r = await RK.assess_requirement_risk(db, tc.project_id, tc.requirement_id,
                                                     changed=False)
                risks[tc.requirement_id] = r["risk"]

    # The impact builder needs project_id for risk; fetch from first change if missing
    items = []
    for tcid, entry in merged.items():
        tc = (await db.execute(select(TestCase).where(TestCase.id == tcid))).scalars().first()
        if not tc:
            continue
        risk = risks.get(tc.requirement_id, "MEDIUM")
        conf = confidences.get(tcid, "Low")
        boost = await _failure_boost(db, tcid)
        etype = await _case_type(db, tcid)
        score = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}[risk] + boost
        if conf == "High":
            score += 1
        if tc.priority in ("HIGH", "CRITICAL"):
            score += 1
        if etype in ("API", "WEB_UI"):
            score += 1  # automated = cheap to run
        if score >= 6:
            tier = "MUST_RUN"
        elif score >= 4:
            tier = "RECOMMENDED"
        else:
            tier = "OPTIONAL"
        if boost >= 2:
            note = "High Regression Value (failed repeatedly)"
        else:
            note = ""
        items.append({
            "test_case_id": tcid, "tc_code": tc.tc_code, "title": tc.title,
            "exec_type": etype, "tier": tier, "risk": risk,
            "impact_confidence": conf, "score": score,
            "reasons": entry["reasons"] + ([note] if note else []),
            "because": sorted(set(entry["because"])),
            "relationship_path": paths.get(tcid, []),
            "est_minutes": TYPE_MINUTES[etype],
        })
    # priority_rank: tier order then score desc
    tier_order = {"MUST_RUN": 0, "RECOMMENDED": 1, "OPTIONAL": 2}
    items.sort(key=lambda x: (tier_order[x["tier"]], -x["score"], x["tc_code"]))
    for i, it in enumerate(items, 1):
        it["priority_rank"] = i
    return {"items": items, "historical_bugs": list(bugs.values())}


def apply_timebox(items: List[Dict[str, Any]],
                  time_budget_min: Optional[int]) -> Dict[str, Any]:
    """Time-constrained scope (§39): keeps P1.., lists excluded + residual risk."""
    if not time_budget_min or time_budget_min <= 0:
        return {"items": items, "excluded": [], "residual_risk": [],
                "used_minutes": sum(i.get("est_minutes", 0) for i in items)}
    kept, excluded = [], []
    used = 0
    for it in items:
        if used + it.get("est_minutes", 0) <= time_budget_min:
            kept.append(it)
            used += it.get("est_minutes", 0)
        else:
            excluded.append(it)
    residual = sorted({f"{e['risk']} risk: {e['tc_code']} {e['title'][:60]}" for e in excluded})
    return {"items": kept, "excluded": excluded, "residual_risk": residual,
            "used_minutes": used, "budget_minutes": time_budget_min}


async def flag_outdated(db: AsyncSession, change_id: str) -> Dict[str, int]:
    """Flags Confirmed-impact automation NEEDS_UPDATE/outdated (vote: flag-now).

    Manual/API cases surface via plan items; API configs + UI scripts get hard flags.
    Returns counts for the response.
    """
    from app.qa.regression_models import ChangeRecord
    change = (await db.execute(select(ChangeRecord).where(
        ChangeRecord.id == change_id))).scalars().first()
    if not change:
        raise ValueError("Change not found")
    impact = await IG.build_impact(db, change_id)
    confirmed = {c["id"] for c in impact["cases"] if c["level"] == "Direct"}
    api_flagged = ui_flagged = 0
    for tcid in confirmed:
        cfg = (await db.execute(select(APITestConfig).where(
            APITestConfig.test_case_id == tcid))).scalars().first()
        if cfg and not cfg.outdated_flag:
            cfg.outdated_flag = True
            api_flagged += 1
        scr = (await db.execute(select(UIAutomationScript).where(
            UIAutomationScript.test_case_id == tcid))).scalars().first()
        if scr and scr.status == "APPROVED":
            scr.status = "NEEDS_UPDATE"
            scr.update_reason = f"Flagged by {change.change_code} — review required"
            ui_flagged += 1
    await db.commit()
    return {"confirmed_cases": len(confirmed),
            "api_flagged": api_flagged, "ui_flagged": ui_flagged}
