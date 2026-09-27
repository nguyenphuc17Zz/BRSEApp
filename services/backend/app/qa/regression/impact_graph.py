"""Impact graph built from REAL relations (DB edges first, LLM only for Possible).

Levels: Direct (1 hop from change seed) / Indirect (2 hops) / Possible (LLM-picked
from a grounded candidate list, confidence Low, Needs Review when thin).
"""
import json
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.models import WorkItem, ProjectRelationship
from app.qa.models import TestCase, AcceptanceCriterion
from app.qa.api_models import APIEndpoint, APITestConfig
from app.qa.ui_models import UIAutomationScript
from app.qa.execution_models import TestExecution
from app.qa.regression_models import ChangeRecord
from app.qa import engines as E1
from app.qa.llm import generate_qa_json

IMPACT_SYSTEM = (
    "You are a senior QA analyst. Pick possibly-affected requirements ONLY from "
    "the provided candidate list (by ID). Never invent IDs. Be conservative."
)


def _node(kind: str, id: str, code: str, title: str, level: str,
          path: List[str], confidence: str) -> Dict[str, Any]:
    return {"kind": kind, "id": id, "code": code, "title": title,
            "level": level, "path": path, "confidence": confidence}


async def _related_ids(db: AsyncSession, project_id: str, source_type: str,
                       source_id: str, relation_types: Optional[List[str]] = None,
                       direction: str = "out") -> List[Any]:
    stmt = select(ProjectRelationship).where(
        ProjectRelationship.project_id == project_id)
    if direction == "out":
        stmt = stmt.where(ProjectRelationship.source_type == source_type,
                          ProjectRelationship.source_id == source_id)
    else:
        stmt = stmt.where(ProjectRelationship.target_type == source_type,
                          ProjectRelationship.target_id == source_id)
    if relation_types:
        stmt = stmt.where(ProjectRelationship.relation_type.in_(relation_types))
    return (await db.execute(stmt)).scalars().all()


async def build_impact(
    db: AsyncSession, change_id: str,
    preferred_provider: Optional[str] = None, model: Optional[str] = None,
) -> Dict[str, Any]:
    change = (await db.execute(select(ChangeRecord).where(
        ChangeRecord.id == change_id))).scalars().first()
    if not change:
        raise ValueError("Change not found")
    pid = change.project_id
    seed_req_ids: List[str] = []
    if change.requirement_id:
        seed_req_ids.append(change.requirement_id)
    if change.decision_id:
        # decisions -> requirements via relations (both directions)
        for rel in await _related_ids(db, pid, "decision", change.decision_id, direction="out"):
            if rel.target_type == "requirement":
                seed_req_ids.append(rel.target_id)
        for rel in await _related_ids(db, pid, "decision", change.decision_id, direction="in"):
            if rel.source_type == "requirement":
                seed_req_ids.append(rel.source_id)
    if change.bug_id:
        for rel in await _related_ids(db, pid, "bug", change.bug_id, direction="out"):
            if rel.target_type in ("requirement", "test_case") and rel.target_type == "requirement":
                seed_req_ids.append(rel.target_id)

    nodes: List[Dict[str, Any]] = []
    seen_cases: Set[str] = set()
    seen_reqs: Set[str] = set(seed_req_ids)
    cases: List[Dict[str, Any]] = []
    apis: List[Dict[str, Any]] = []
    uis: List[Dict[str, Any]] = []
    bugs: List[Dict[str, Any]] = []

    async def _req_title(rid: str) -> Tuple[str, str]:
        item = await E1.get_requirement(db, rid)
        if not item:
            return "", ""
        return getattr(item, "req_code", "") or "", item.title

    # --- Direct: seed requirements + their cases/ACs ---
    for rid in seed_req_ids:
        code, title = await _req_title(rid)
        nodes.append(_node("requirement", rid, code, title, "Direct",
                           [f"change:{change.change_code}"], "High"))
        req_cases = (await db.execute(select(TestCase).where(
            TestCase.requirement_id == rid,
            TestCase.status != "REJECTED"))).scalars().all()
        for tc in req_cases:
            if tc.id in seen_cases:
                continue
            seen_cases.add(tc.id)
            cases.append(_node("test_case", tc.id, tc.tc_code, tc.title, "Direct",
                               [f"change:{change.change_code}", f"requirement:{code or rid[:6]}"],
                               "High"))
        # ACs of this requirement (context for drift checks)
        acs = (await db.execute(select(AcceptanceCriterion).where(
            AcceptanceCriterion.requirement_id == rid))).scalars().all()
        for a in acs:
            nodes.append(_node("acceptance_criterion", a.id, a.ac_code,
                               f"Given {a.given_text[:60]}...", "Direct",
                               [f"change:{change.change_code}", f"requirement:{code or rid[:6]}"],
                               "High"))

    # --- Indirect level 1: requirement dependencies (depends_on / related_to, both directions) ---
    indirect_reqs: List[str] = []
    for rid in seed_req_ids:
        for direction in ("out", "in"):
            for rel in await _related_ids(
                    db, pid, "requirement", rid,
                    ["depends_on", "related_to", "implemented_by"], direction=direction):
                other = rel.target_id if direction == "out" else rel.source_id
                otype = rel.target_type if direction == "out" else rel.source_type
                if otype == "requirement" and other not in seen_reqs:
                    seen_reqs.add(other)
                    indirect_reqs.append(other)
                    code, title = await _req_title(other)
                    nodes.append(_node("requirement", other, code, title, "Indirect",
                                       [f"change:{change.change_code}",
                                        f"requirement:{rid[:6]}",
                                        f"relation:{rel.relation_type}"], "Medium"))
    for rid in indirect_reqs:
        req_cases = (await db.execute(select(TestCase).where(
            TestCase.requirement_id == rid,
            TestCase.status != "REJECTED"))).scalars().all()
        for tc in req_cases:
            if tc.id in seen_cases:
                continue
            seen_cases.add(tc.id)
            cases.append(_node("test_case", tc.id, tc.tc_code, tc.title, "Indirect",
                               [f"requirement:{rid[:6]} (dependency)"], "Medium"))

    # --- Indirect level 2: shared API endpoints / UI mappings ---
    if seen_cases:
        cfg_rows = (await db.execute(select(APITestConfig).where(
            APITestConfig.test_case_id.in_(list(seen_cases))))).scalars().all()
        ep_ids = {c.endpoint_id for c in cfg_rows if c.endpoint_id}
        for eid in ep_ids:
            ep = (await db.execute(select(APIEndpoint).where(APIEndpoint.id == eid))).scalars().first()
            if ep:
                apis.append(_node("api", ep.id, f"{ep.method} {ep.path}", ep.name or ep.path,
                                  "Indirect", ["shared endpoint with affected case"], "Medium"))
        # sibling cases on same endpoints (data-flow neighbors)
        if ep_ids:
            sib_cfgs = (await db.execute(select(APITestConfig).where(
                APITestConfig.endpoint_id.in_(list(ep_ids))))).scalars().all()
            for sc in sib_cfgs:
                if sc.test_case_id in seen_cases:
                    continue
                tc = (await db.execute(select(TestCase).where(
                    TestCase.id == sc.test_case_id))).scalars().first()
                if tc and tc.status != "REJECTED":
                    seen_cases.add(tc.id)
                    cases.append(_node("test_case", tc.id, tc.tc_code, tc.title, "Indirect",
                                       ["shared API endpoint"], "Medium"))
        # UI scripts among affected cases
        ui_rows = (await db.execute(select(UIAutomationScript).where(
            UIAutomationScript.test_case_id.in_(list(seen_cases))))).scalars().all()
        for s in ui_rows:
            uis.append(_node("ui_automation", s.test_case_id, "", f"script v{s.script_version} ({s.status})",
                             "Indirect", ["automated case"], "Medium"))

    # --- Historical bugs on affected cases/requirements ---
    bug_ids: Set[str] = set()
    if seen_cases:
        ex_rows = (await db.execute(select(TestExecution.bug_work_item_id).where(
            TestExecution.test_case_id.in_(list(seen_cases)),
            TestExecution.bug_work_item_id.isnot(None)))).scalars().all()
        bug_ids.update(ex_rows)
    for rid in seen_reqs:
        for rel in await _related_ids(db, pid, "requirement", rid,
                                      ["found_in", "related_to"], direction="in"):
            if rel.source_type == "bug":
                bug_ids.add(rel.source_id)
    for bid in bug_ids:
        b = (await db.execute(select(WorkItem).where(WorkItem.id == bid))).scalars().first()
        if b and b.status != "REJECTED":
            bugs.append(_node("bug", b.id, getattr(b, "req_code", "") or "",
                              b.title, "Indirect", ["history on affected area"], "Medium"))

    # --- Possible: LLM picks from grounded project requirement list ---
    possible: List[Dict[str, Any]] = []
    if seed_req_ids:
        all_reqs = (await db.execute(select(WorkItem).where(
            WorkItem.project_id == pid, WorkItem.item_type == "REQUIREMENT").order_by(
            WorkItem.created_at.desc()).limit(40))).scalars().all()
        cand_lines = [f"- [{r.id}] {(getattr(r, 'req_code', '') or '')} {r.title[:100]}"
                      for r in all_reqs if r.id not in seen_reqs]
        if cand_lines:
            prompt = f"""Change: {change.change_summary[:800]}
Already confirmed affected: {sorted(seen_reqs)}
Candidate requirements (pick by ID only):
{chr(10).join(cand_lines[:40])}
Return strict JSON: {{"possible": [{{"id": "<work item id>", "reason": "..."}}]}} (max 5, empty ok)"""
            parsed = await generate_qa_json(prompt, IMPACT_SYSTEM,
                                            preferred_provider, model, max_tokens=600)
            valid_ids = {r.id for r in all_reqs}
            if isinstance(parsed, dict) and isinstance(parsed.get("possible"), list):
                for p in parsed["possible"][:5]:
                    if isinstance(p, dict) and p.get("id") in valid_ids and p["id"] not in seen_reqs:
                        seen_reqs.add(p["id"])
                        code, title = await _req_title(p["id"])
                        possible.append(_node("requirement", p["id"], code, title, "Possible",
                                              ["LLM suggestion — Needs Review"],
                                              "Low"))
                        nodes.append(possible[-1])
    return {"change_id": change.id, "change_code": change.change_code,
            "seed_requirements": seed_req_ids,
            "nodes": nodes, "cases": cases, "apis": apis, "uis": uis,
            "bugs": bugs, "possible": possible}
