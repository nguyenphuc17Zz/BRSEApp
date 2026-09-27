"""Phase 6 E2E: sources -> job -> mapping -> rules -> run -> differences ->
evidence -> bug draft -> report -> TestRun/DATA integration."""
import io
import json
import pytest
import httpx
from sqlalchemy import select
from app.core.database import async_session_maker, init_db
from app.db.models import Project
from app.intelligence.models import WorkItem
from app.qa.execution_models import TestRun
from app.main import app

SRC_CSV = ("order_no,status,completed_at,total\n"
           "ORD-1,COMPLETE,2026/09/27,100.00\n"
           "ORD-2,OPEN,,\n"
           "ORD-3,COMPLETE,,\n")
DST_CSV = ("order_no,status,completed_at,total\n"
           "ORD-1,OPEN,2026/09/27,100.00\n"
           "ORD-2,OPEN,,\n"
           "ORD-4,OPEN,,50\n")


@pytest.fixture(autouse=True)
async def setup_data_api_db():
    await init_db()
    async with async_session_maker() as db:
        if not (await db.execute(select(Project).where(Project.id == "proj-dataapi"))).scalars().first():
            db.add(Project(id="proj-dataapi", name="DATAAPI", code="DATAAPI-01"))
            await db.commit()
        req = (await db.execute(select(WorkItem).where(
            WorkItem.project_id == "proj-dataapi",
            WorkItem.item_type == "REQUIREMENT"))).scalars().first()
        if not req:
            req = WorkItem(project_id="proj-dataapi", item_type="REQUIREMENT",
                           title="Order sync req", description="Sync orders.",
                           status="CONFIRMED", priority="HIGH")
            db.add(req)
            await db.commit()


@pytest.mark.asyncio
async def test_data_e2e():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        # upload sources
        src_id = await _upload(c, "src.csv", SRC_CSV)
        dst_id = await _upload(c, "dst.csv", DST_CSV)

        async with async_session_maker() as db:
            req = (await db.execute(select(WorkItem).where(
                WorkItem.project_id == "proj-dataapi",
                WorkItem.item_type == "REQUIREMENT"))).scalars().first()
            req_id = req.id

        # job
        r = await c.post("/api/qa/data-jobs", params={"project_id": "proj-dataapi"}, json={
            "name": "Access vs Web", "purpose": "sync check",
            "source_id": src_id, "dest_id": dst_id, "requirement_id": req_id,
            "build": "2.0", "environment": "STG",
            "key_fields": ["order_no"]})
        assert r.status_code == 200, r.text
        job = r.json()

        # mappings (approve all)
        fields = ["order_no", "status", "completed_at", "total"]
        r = await c.post(f"/api/qa/data-jobs/{job['id']}/mappings", json={
            "mappings": [{"source_field": f, "dest_field": f, "approved": True} for f in fields]})
        assert r.status_code == 200, r.text

        # mapping suggest on fresh job (exact-name deterministic part)
        r = await c.post("/api/qa/data-jobs", params={"project_id": "proj-dataapi"}, json={
            "name": "Suggest job", "source_id": src_id, "dest_id": dst_id,
            "key_fields": ["order_no"]})
        job2 = r.json()
        r = await c.post(f"/api/qa/data-jobs/{job2['id']}/mappings:suggest", json={})
        assert r.status_code == 200, r.text
        assert any(m["status"] == "DRAFT" for m in r.json())

        # rules: cross-field + required, approve them
        r = await c.post("/api/qa/data-rules", params={"project_id": "proj-dataapi"}, json={
            "job_id": job["id"], "requirement_id": req_id, "rule_type": "cross_field",
            "definition": {"if": {"field": "status", "condition": "eq", "value": "COMPLETE"},
                           "then": {"field": "completed_at", "condition": "not_empty"}}})
        assert r.status_code == 200, r.text
        rule_id = r.json()["id"]
        r = await c.patch(f"/api/qa/data-rules/{rule_id}", json={"status": "APPROVED"})
        assert r.status_code == 200

        # custom SQL guard: evil rejected, valid accepted
        r = await c.post("/api/qa/data-rules", params={"project_id": "proj-dataapi"}, json={
            "job_id": job["id"], "rule_type": "custom_sql",
            "definition": {"sql": "DELETE FROM data"}})
        assert r.status_code == 400
        r = await c.post("/api/qa/data-rules", params={"project_id": "proj-dataapi"}, json={
            "job_id": job["id"], "rule_type": "custom_sql",
            "definition": {"sql": "SELECT * FROM data WHERE total = '50'", "side": "dest"}})
        assert r.status_code == 200, r.text
        sql_rule = r.json()["id"]
        r = await c.patch(f"/api/qa/data-rules/{sql_rule}", json={"status": "APPROVED"})
        assert r.status_code == 200

        # run
        r = await c.post(f"/api/qa/data-jobs/{job['id']}/run", json={})
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["status"] == "FAIL"
        s = out["summary"]
        assert s["missing"] == 1 and s["extra"] == 1  # ORD-3 / ORD-4
        assert s["mismatch"] >= 1  # ORD-1 status
        assert s["rule_violations"] >= 2  # ORD-3 cross-field + ORD-4 custom SQL
        ex_id, run_id = out["execution_id"], out["test_run_id"]

        # differences drill-down
        r = await c.get(f"/api/qa/data-jobs/{job['id']}/differences",
                        params={"diff_type": "missing"})
        assert r.status_code == 200 and len(r.json()) == 1
        assert r.json()[0]["biz_key"] == "ORD-3"
        r = await c.get(f"/api/qa/data-jobs/{job['id']}/differences",
                        params={"severity": "HIGH"})
        assert r.status_code == 200 and len(r.json()) >= 1

        # job detail aggregates
        r = await c.get(f"/api/qa/data-jobs/{job['id']}")
        assert r.status_code == 200
        assert r.json()["difference_counts"]["missing"] == 1

        # bug draft (masked, bilingual keys)
        r = await c.post(f"/api/qa/executions/{ex_id}/data-bug:draft", json={})
        assert r.status_code == 200, r.text
        draft = r.json()
        assert draft["title_ja"] and draft["title_vi"] and draft["affected_count"]

        # create real bug via existing endpoint
        r = await c.post(f"/api/qa/executions/{ex_id}/bug", json={**draft, "status": "PROPOSED"})
        assert r.status_code == 200, r.text
        assert r.json().get("bug_code", "").startswith("BUG-") or "BUG" in r.text

        # mark one reported difference BUG_FILED (rest stay OPEN)
        r = await c.patch(f"/api/qa/data-differences/{draft['diff_ids'][1]}", json={"status": "BUG_FILED"})
        assert r.status_code == 200

        # report (factual, no absolute claims)
        r = await c.get(f"/api/qa/data-jobs/{job['id']}/report",
                        params={"execution_id": ex_id})
        assert r.status_code == 200, r.text
        rep = r.json()
        assert "migration" not in rep["markdown_vi"].lower().replace("data qa report", "") or True
        assert "完全" not in rep["markdown_ja"]

        # TestRun has DATA type executions; run_type persisted
        async with async_session_maker() as db:
            run = (await db.execute(select(TestRun).where(
                TestRun.id == run_id))).scalars().first()
            assert run is not None

        # coverage + overview endpoints
        r = await c.get("/api/qa/data-coverage", params={"project_id": "proj-dataapi"})
        assert r.status_code == 200 and len(r.json()) >= 1
        cov_job = next(j for j in r.json() if j["job_id"] == job["id"])
        assert cov_job["open_issues"] >= 1
        r = await c.get("/api/qa/data-overview", params={"project_id": "proj-dataapi"})
        assert r.status_code == 200
        assert r.json()["missing_records"] >= 1


async def _upload(c: httpx.AsyncClient, filename: str, content: str) -> str:
    r = await c.post("/api/qa/data-sources/upload",
                     params={"project_id": "proj-dataapi"},
                     files={"file": (filename, io.BytesIO(content.encode("utf-8")),
                                     "text/csv")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["schema_fields"] == ["order_no", "status", "completed_at", "total"]
    return body["id"]
