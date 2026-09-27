"""API-level E2E for QA Phase 2: router validation, upload, serialization (no lifespan)."""
import io
import pytest
import httpx
from sqlalchemy import select
from app.core.database import async_session_maker, init_db
from app.db.models import Project
from app.intelligence.models import WorkItem
from app.qa.models import TestCase
from app.main import app


@pytest.fixture(autouse=True)
async def setup_api_db():
    await init_db()
    async with async_session_maker() as db:
        if not (await db.execute(select(Project).where(Project.id == "proj-qa2api"))).scalars().first():
            db.add(Project(id="proj-qa2api", name="QA2 API", code="QA2-API-01"))
            await db.commit()
        req = (await db.execute(select(WorkItem).where(
            WorkItem.project_id == "proj-qa2api", WorkItem.item_type == "REQUIREMENT"))).scalars().first()
        if not req:
            req = WorkItem(project_id="proj-qa2api", item_type="REQUIREMENT",
                           title="API req", description="API desc", status="CONFIRMED")
            db.add(req)
            await db.flush()
            db.add(TestCase(project_id="proj-qa2api", tc_code="TC-001", title="API case",
                            purpose="p", case_type="Happy", priority="HIGH",
                            expected_result="ok", requirement_id=req.id,
                            evidence_quote="q", knowledge_class="Confirmed",
                            source="Manual", ai_generated=False, confidence=1.0,
                            status="APPROVED"))
            await db.commit()


@pytest.mark.asyncio
async def test_api_e2e_run_to_report():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        # create run
        r = await c.post("/api/qa/test-runs", params={"project_id": "proj-qa2api"}, json={
            "name": "E2E build", "version_build": "9.9.9", "environment": "STG", "tester": "e2e"})
        assert r.status_code == 200, r.text
        run = r.json()

        # add approved cases
        r = await c.post(f"/api/qa/test-runs/{run['id']}/cases", json={"scope": {"approved_only": True}})
        assert r.status_code == 200, r.text
        assert r.json()["added"] >= 1

        # run detail
        r = await c.get(f"/api/qa/test-runs/{run['id']}")
        assert r.status_code == 200
        ex_id = r.json()["executions"][0]["id"]

        # FAIL without actual -> 400
        r = await c.post(f"/api/qa/executions/{ex_id}/result", json={"status": "FAIL"})
        assert r.status_code == 400

        # FAIL with actual
        r = await c.post(f"/api/qa/executions/{ex_id}/result",
                         json={"status": "FAIL", "actual_result": "crashed on save"})
        assert r.status_code == 200, r.text

        # text evidence + file upload
        r = await c.post(f"/api/qa/executions/{ex_id}/evidence",
                         json={"evidence_type": "note", "title": "n", "text_content": "t"})
        assert r.status_code == 200, r.text
        r = await c.post(f"/api/qa/executions/{ex_id}/evidence/upload",
                         files={"file": ("shot.png", io.BytesIO(b"fakepng"), "image/png")})
        assert r.status_code == 200, r.text
        ev_id = r.json()["id"]

        # serve file inline
        r = await c.get(f"/api/qa/evidence/{ev_id}/file")
        assert r.status_code == 200 and r.content == b"fakepng"

        # bug draft + create
        r = await c.post(f"/api/qa/executions/{ex_id}/bug:draft", json={})
        assert r.status_code == 200, r.text
        draft = r.json()
        r = await c.post(f"/api/qa/executions/{ex_id}/bug",
                         json={**draft, "title_vi": "E2E bug", "status": "PROPOSED"})
        assert r.status_code == 200, r.text
        bug = r.json()
        assert bug["bug_code"].startswith("BUG-")
        assert bug["test_run_id"] == run["id"]

        # bug list filter by run
        r = await c.get("/api/qa/bugs", params={"project_id": "proj-qa2api",
                                                "test_run_id": run["id"]})
        assert r.status_code == 200 and len(r.json()) >= 1

        # retest -> PASS
        r = await c.post(f"/api/qa/executions/{ex_id}/retest", json={})
        assert r.status_code == 200, r.text
        rt_id = r.json()["id"]
        r = await c.post(f"/api/qa/executions/{rt_id}/result",
                         json={"status": "PASS", "actual_result": "fixed"})
        assert r.status_code == 200

        # execution detail has attempts history
        r = await c.get(f"/api/qa/executions/{rt_id}")
        assert r.status_code == 200 and len(r.json()["attempts"]) == 2

        # execution coverage + overview
        r = await c.get("/api/qa/execution-coverage", params={"project_id": "proj-qa2api"})
        assert r.status_code == 200 and r.json()[0]["exec_status"] == "Passed"
        r = await c.get("/api/qa/projects/proj-qa2api/overview")
        assert r.status_code == 200 and r.json()["open_bugs"] >= 1

        # report generate
        r = await c.post(f"/api/qa/test-runs/{run['id']}/reports",
                         json={"report_type": "completion"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "DRAFT" and r.json()["markdown_ja"]
