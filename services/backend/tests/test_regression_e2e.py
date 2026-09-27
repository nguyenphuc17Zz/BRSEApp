"""Phase 5 API E2E: change -> analyze -> plan -> approve -> REGRESSION run -> summary."""
import pytest
import httpx
from sqlalchemy import select
from app.core.database import async_session_maker, init_db
from app.db.models import Project
from app.intelligence.models import WorkItem
from app.qa.models import TestCase, AcceptanceCriterion
from app.main import app


@pytest.fixture(autouse=True)
async def setup_reg_api_db():
    await init_db()
    async with async_session_maker() as db:
        if not (await db.execute(select(Project).where(Project.id == "proj-regapi"))).scalars().first():
            db.add(Project(id="proj-regapi", name="REGAPI", code="REGAPI-01"))
            await db.commit()
        req = (await db.execute(select(WorkItem).where(
            WorkItem.project_id == "proj-regapi",
            WorkItem.item_type == "REQUIREMENT"))).scalars().first()
        if not req:
            req = WorkItem(project_id="proj-regapi", item_type="REQUIREMENT",
                           title="Search exact match", description="Exact only.",
                           status="CONFIRMED", priority="HIGH")
            db.add(req)
            await db.flush()
            db.add(AcceptanceCriterion(project_id="proj-regapi", requirement_id=req.id,
                                       ac_code="AC-001", given_text="g", when_text="w",
                                       then_text="exact", status="APPROVED"))
            for code, title in [("TC-101", "Search exact"), ("TC-102", "Empty query")]:
                db.add(TestCase(project_id="proj-regapi", tc_code=code, title=title,
                                purpose="p", case_type="Happy", priority="HIGH",
                                expected_result="ok", requirement_id=req.id,
                                evidence_quote="q", knowledge_class="Confirmed",
                                source="Manual", ai_generated=False, confidence=1.0,
                                status="APPROVED"))
            await db.commit()


@pytest.mark.asyncio
async def test_regression_e2e():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        # suggest (may be empty) + create change
        r = await c.get("/api/qa/changes/suggest", params={"project_id": "proj-regapi"})
        assert r.status_code == 200
        async with async_session_maker() as db:
            req = (await db.execute(select(WorkItem).where(
                WorkItem.project_id == "proj-regapi",
                WorkItem.item_type == "REQUIREMENT"))).scalars().first()
            req_id = req.id
        r = await c.post("/api/qa/changes", params={"project_id": "proj-regapi"}, json={
            "source": "requirement_update", "requirement_id": req_id,
            "new_snapshot": {"title": "Search partial match",
                             "description": "Partial supported."},
            "hint": "exact -> partial"})
        assert r.status_code == 200, r.text
        change = r.json()
        assert change["change_code"].startswith("CR-")

        # analyze: diff + impact + risk + flags
        r = await c.post(f"/api/qa/changes/{change['id']}/analyze", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["change"]["status"] == "ANALYZED"
        assert body["impact"]["cases"]
        assert body["before_after"]["aspects"]

        # versions recorded
        r = await c.get(f"/api/qa/requirements/{req_id}/versions")
        assert r.status_code == 200 and len(r.json()) >= 1

        # plan with time-box
        r = await c.post("/api/qa/plans", params={"project_id": "proj-regapi"}, json={
            "change_ids": [change["id"]], "release_tag": "2.5", "time_budget_min": 60})
        assert r.status_code == 200, r.text
        plan = r.json()
        assert plan["plan_code"].startswith("RP-")
        assert plan["item_count"] >= 1

        r = await c.get(f"/api/qa/plans/{plan['id']}")
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(i["reason"] and i["relationship_path"] for i in items)
        first_item = items[0]["id"]

        # user add duplicate -> 400; remove + re-add ok
        r = await c.delete(f"/api/qa/plans/items/{first_item}")
        assert r.status_code == 200
        # re-add same case manually
        async with async_session_maker() as db:
            tc = (await db.execute(select(TestCase).where(
                TestCase.project_id == "proj-regapi"))).scalars().first()
            add_id = tc.id
        r = await c.post(f"/api/qa/plans/{plan['id']}/items",
                         json={"test_case_id": add_id, "tier": "MUST_RUN",
                               "reason": "user added"})
        assert r.status_code == 200, r.text

        # approve + run -> REGRESSION run
        r = await c.patch(f"/api/qa/plans/{plan['id']}", json={"status": "APPROVED"})
        assert r.status_code == 200
        r = await c.post(f"/api/qa/plans/{plan['id']}/run",
                         json={"version_build": "2.5.0", "environment": "STG"})
        assert r.status_code == 200, r.text
        run_id = r.json()["test_run_id"]
        assert r.json()["added"] >= 1

        # execute one case manually via run executions
        r = await c.get(f"/api/qa/test-runs/{run_id}")
        assert r.status_code == 200
        ex_id = r.json()["executions"][0]["id"]
        r = await c.post(f"/api/qa/executions/{ex_id}/result",
                         json={"status": "PASS", "actual_result": "ok"})
        assert r.status_code == 200

        # summary + change coverage
        r = await c.get(f"/api/qa/plans/{plan['id']}/summary")
        assert r.status_code == 200
        assert r.json()["passed"] >= 1 and r.json()["recommended"] >= 1
        r = await c.get("/api/qa/change-coverage", params={"plan_id": plan["id"]})
        assert r.status_code == 200
        cov = r.json()
        assert cov["affected_cases"] >= 1 and cov["executed"] >= 1

        # run_type persisted
        async with async_session_maker() as db:
            from app.qa.execution_models import TestRun
            run = (await db.execute(select(TestRun).where(
                TestRun.id == run_id))).scalars().first()
            assert run.run_type == "REGRESSION"
