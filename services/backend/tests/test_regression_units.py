"""Phase 5 unit tests: change classification fallback, risk scoring, tiers, time-box, dedupe."""
import pytest
from sqlalchemy import select
from app.core.database import async_session_maker, init_db
from app.db.models import Project
from app.intelligence.models import WorkItem, ProjectRelationship
from app.qa.models import TestCase, AcceptanceCriterion
from app.qa.execution_models import TestRun, TestExecution
from app.qa.regression import change_engine as CE
from app.qa.regression import risk_engine as RK
from app.qa.regression import recommender as RC


@pytest.fixture(autouse=True)
async def setup_reg_db():
    await init_db()
    async with async_session_maker() as db:
        if not (await db.execute(select(Project).where(Project.id == "proj-reg"))).scalars().first():
            db.add(Project(id="proj-reg", name="REG", code="REG-01"))
            await db.commit()


async def _seed(db):
    req = WorkItem(project_id="proj-reg", item_type="REQUIREMENT",
                   title="Search exact match", description="Search supports exact match.",
                   status="CONFIRMED", priority="HIGH")
    db.add(req)
    await db.flush()
    dep = WorkItem(project_id="proj-reg", item_type="REQUIREMENT",
                   title="Pagination", description="Paginate results.",
                   status="CONFIRMED", priority="MEDIUM")
    db.add(dep)
    await db.flush()
    db.add(ProjectRelationship(project_id="proj-reg", source_type="requirement",
                               source_id=dep.id, target_type="requirement",
                               target_id=req.id, relation_type="depends_on"))
    ac = AcceptanceCriterion(project_id="proj-reg", requirement_id=req.id,
                             ac_code="AC-001", given_text="g", when_text="w",
                             then_text="t", status="APPROVED")
    db.add(ac)
    await db.flush()
    cases = []
    for code, title, prio in [("TC-101", "Search exact", "HIGH"),
                              ("TC-102", "Search partial", "MEDIUM"),
                              ("TC-150", "Pagination", "MEDIUM")]:
        tc = TestCase(project_id="proj-reg", tc_code=code, title=title,
                      purpose="p", case_type="Happy", priority=prio,
                      expected_result="ok", requirement_id=req.id if code != "TC-150" else dep.id,
                      evidence_quote="q", knowledge_class="Confirmed",
                      source="Manual", ai_generated=False, confidence=1.0,
                      status="APPROVED")
        db.add(tc)
        await db.flush()
        cases.append(tc)
    await db.commit()
    return req, dep, cases


@pytest.mark.asyncio
async def test_change_create_classify_version():
    async with async_session_maker() as db:
        req, _, _ = await _seed(db)
        change = await CE.create_change(db, "proj-reg", {
            "source": "requirement_update", "requirement_id": req.id,
            "new_snapshot": {"title": "Search partial match",
                             "description": "Search supports partial match."},
            "hint": "exact -> partial",
        }, changed_by="qa")
        assert change.change_code.startswith("CR-")
        cats = __import__("json").loads(change.categories_json)
        assert isinstance(cats, list) and cats
        assert change.business_summary
        # version snapshot taken
        from app.qa.regression_models import RequirementVersion
        vers = (await db.execute(select(RequirementVersion).where(
            RequirementVersion.requirement_id == req.id))).scalars().all()
        assert len(vers) == 1 and vers[0].version_no == 1


@pytest.mark.asyncio
async def test_risk_explains_reasons():
    async with async_session_maker() as db:
        req, _, _ = await _seed(db)
        r = await RK.assess_requirement_risk(db, "proj-reg", req.id, changed=True)
        assert r["risk"] in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
        assert r["reasons"]
        assert any("HIGH" in x for x in r["reasons"])


@pytest.mark.asyncio
async def test_recommend_tiers_reasons_timebox():
    async with async_session_maker() as db:
        req, dep, cases = await _seed(db)
        # failing history on TC-101 -> boost
        run = TestRun(project_id="proj-reg", run_code="RUN-01", name="r1")
        db.add(run)
        await db.flush()
        for st in ["PASS", "FAIL", "PASS", "FAIL"]:
            db.add(TestExecution(test_run_id=run.id, test_case_id=cases[0].id,
                                 requirement_id=req.id, status=st))
        await db.commit()
        change = await CE.create_change(db, "proj-reg", {
            "source": "requirement_update", "requirement_id": req.id,
            "new_snapshot": {"title": "Search partial match", "description": "x"},
        })
        rec = await RC.recommend_for_changes(db, [change.id])
        ids = [i["test_case_id"] for i in rec["items"]]
        assert cases[0].id in ids  # direct
        assert cases[2].id in ids  # via depends_on (indirect)
        for it in rec["items"]:
            assert it["reasons"] and it["relationship_path"] and it["tier"] in (
                "MUST_RUN", "RECOMMENDED", "OPTIONAL")
        # TC-101 failing history -> top rank / MUST
        first = rec["items"][0]
        assert first["test_case_id"] == cases[0].id
        assert any("High Regression Value" in r for r in first["reasons"])
        boxed = RC.apply_timebox(rec["items"], 5)
        assert boxed["excluded"]
        assert boxed["residual_risk"]
        assert boxed["used_minutes"] <= 5


@pytest.mark.asyncio
async def test_flag_outdated_and_dedupe():
    async with async_session_maker() as db:
        from app.qa.api_models import APITestConfig
        req, _, cases = await _seed(db)
        db.add(APITestConfig(test_case_id=cases[1].id, method="GET",
                             url_template="https://x/s", expected_status=200))
        await db.commit()
        c1 = await CE.create_change(db, "proj-reg", {
            "source": "requirement_update", "requirement_id": req.id,
            "new_snapshot": {"title": "T2", "description": "x"}})
        c2 = await CE.create_change(db, "proj-reg", {
            "source": "ac_change", "requirement_id": req.id,
            "new_snapshot": {"title": "T3", "description": "y"}})
        flags = await RC.flag_outdated(db, c1.id)
        assert flags["confirmed_cases"] >= 2 and flags["api_flagged"] == 1
        rec = await RC.recommend_for_changes(db, [c1.id, c2.id])
        seen = [i["test_case_id"] for i in rec["items"]]
        assert len(seen) == len(set(seen))  # deduped
        both = [i for i in rec["items"] if len(i["because"]) == 2]
        assert both  # shared case keeps both reasons
