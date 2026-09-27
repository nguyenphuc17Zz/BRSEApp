"""Phase 3 runner + API E2E: mock transport execution, suite, evidence, bug, coverage."""
import json
import pytest
import httpx
from sqlalchemy import select
from app.core.database import async_session_maker, init_db
from app.db.models import Project
from app.intelligence.models import WorkItem
from app.qa.models import TestCase
from app.qa.api_models import APIEndpoint, APIEnvironment, APITestConfig, APIAssertion
from app.qa.execution_models import TestEvidence
from app.qa.api_testing import runner as RN
from app.main import app


@pytest.fixture(autouse=True)
async def setup_api3_db():
    await init_db()
    async with async_session_maker() as db:
        if not (await db.execute(select(Project).where(Project.id == "proj-qa3"))).scalars().first():
            db.add(Project(id="proj-qa3", name="QA3 API", code="QA3-01"))
            await db.commit()


async def _seed(db, path="/api/users", method="POST", status="APPROVED"):
    req = WorkItem(project_id="proj-qa3", item_type="REQUIREMENT",
                   title="User API req", description="Manage users.", status="CONFIRMED")
    db.add(req)
    await db.flush()
    ep = APIEndpoint(project_id="proj-qa3", method=method, path=path,
                     name=f"{method} {path}", spec_source="manual")
    db.add(ep)
    await db.flush()
    env = APIEnvironment(project_id="proj-qa3", name="STG",
                         base_url="https://api.example.com", is_default=True)
    db.add(env)
    await db.flush()
    tc = TestCase(project_id="proj-qa3", tc_code="TC-090", title=f"{method} {path} valid",
                  purpose="p", case_type="Happy", priority="HIGH",
                  expected_result="2xx", requirement_id=req.id,
                  evidence_quote="q", knowledge_class="Confirmed",
                  source="Manual", ai_generated=False, confidence=1.0, status=status)
    db.add(tc)
    await db.flush()
    cfg = APITestConfig(test_case_id=tc.id, endpoint_id=ep.id, method=method,
                        url_template="{{BASE_URL}}" + path,
                        body_text='{"email": "{{TEST_EMAIL}}"}',
                        expected_status=201)
    db.add(cfg)
    await db.flush()
    db.add(APIAssertion(test_case_id=tc.id, field="json", target="data.id",
                        operator="exists", status="APPROVED", ai_generated=False))
    await db.commit()
    return req, ep, env, tc


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_runner_pass_with_mock():
    async with async_session_maker() as db:
        _, _, env, tc = await _seed(db)
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            seen["body"] = request.content.decode()
            return httpx.Response(201, json={"data": {"id": 9}}, headers={"Content-Type": "application/json"})

        out = await RN.execute_api_case(db, tc.id, env.id, {}, None, _transport(handler), "qa")
        assert out["status"] == "PASS"
        assert "users" in seen["url"] and "@example.com" in seen["body"]  # dynamic data resolved
        assert out["extracted"] == {}
        ev = (await db.execute(select(TestEvidence).where(
            TestEvidence.execution_id == out["execution_id"]))).scalars().all()
        kinds = {e.evidence_type for e in ev}
        assert {"api_request", "api_response"} <= kinds


@pytest.mark.asyncio
async def test_runner_fail_records_failed_assertion_and_extracts():
    async with async_session_maker() as db:
        _, _, env, tc = await _seed(db, path="/api/login", method="POST")
        async with async_session_maker() as db2:
            cfg = (await db2.execute(select(APITestConfig).where(
                APITestConfig.test_case_id == tc.id))).scalars().first()
            cfg.extract_map_json = json.dumps({"user_id": "data.id"})
            await db2.commit()

        def handler(request):
            return httpx.Response(200, json={"data": {"id": 5}})

        out = await RN.execute_api_case(db, tc.id, env.id, {}, None, _transport(handler), "qa")
        assert out["status"] == "FAIL"  # status 200 != expected 201
        assert out["extracted"] == {"user_id": 5}  # extracts still work
        assert any(not r["passed"] for r in out["assertions"]["results"])


@pytest.mark.asyncio
async def test_runner_auth_secret_redacted_in_evidence():
    from app.core.security import encrypt_credential
    async with async_session_maker() as db:
        _, _, env, tc = await _seed(db, path="/api/me", method="GET")
        secrets = {"AUTH_TOKEN": encrypt_credential("super-secret-token")}
        env.secrets_json = json.dumps(secrets)
        cfg = (await db.execute(select(APITestConfig).where(
            APITestConfig.test_case_id == tc.id))).scalars().first()
        cfg.auth_ref_json = json.dumps({"type": "bearer", "secret_key": "AUTH_TOKEN"})
        cfg.expected_status = 200
        await db.commit()

        def handler(request):
            assert request.headers["Authorization"] == "Bearer super-secret-token"  # sent live
            return httpx.Response(200, json={"data": {"id": 1}})

        out = await RN.execute_api_case(db, tc.id, env.id, {}, None, _transport(handler), "qa")
        assert out["status"] == "PASS"
        assert "super-secret-token" not in json.dumps(out["request"])
        assert "super-secret-token" not in json.dumps(out["response"])
        ev = (await db.execute(select(TestEvidence).where(
            TestEvidence.execution_id == out["execution_id"]))).scalars().all()
        assert "super-secret-token" not in json.dumps([e.text_content for e in ev])


@pytest.mark.asyncio
async def test_runner_prod_guard_and_network_classification():
    async with async_session_maker() as db:
        _, _, env, tc = await _seed(db, path="/api/users", method="DELETE")
        env.name = "PROD"
        env.base_url = "https://prod.example.com"
        await db.commit()
        with pytest.raises(ValueError, match="ProductionGuard"):
            await RN.execute_api_case(db, tc.id, env.id, {}, None, None, "qa")
        out = await RN.execute_api_case(db, tc.id, env.id, {}, None, None, "qa", confirm_prod=True)

        def boom(request):
            raise httpx.ConnectError("dns fail name resolution")

        # non-prod env for network test
        env.name = "STG"
        env.base_url = "https://stg.example.com"
        await db.commit()
        out2 = await RN.execute_api_case(db, tc.id, env.id, {}, None, _transport(boom), "qa")
        assert out2["status"] == "FAIL" and out2["error_kind"] in ("network", "dns")


@pytest.mark.asyncio
async def test_suite_shares_run_and_chains_vars():
    async with async_session_maker() as db:
        _, _, env, tc1 = await _seed(db, path="/api/users", method="POST")
        _, _, _, tc2 = await _seed(db, path="/api/users/{id}", method="GET")
        async with async_session_maker() as db2:
            cfg2 = (await db2.execute(select(APITestConfig).where(
                APITestConfig.test_case_id == tc2.id))).scalars().first()
            cfg2.expected_status = 200
            cfg2.url_template = "{{BASE_URL}}/api/users/{{uid}}"
            db2.add(APIAssertion(test_case_id=tc2.id, field="status", target="",
                                 operator="eq", expected_value="200",
                                 status="APPROVED", ai_generated=False))
            cfg1 = (await db2.execute(select(APITestConfig).where(
                APITestConfig.test_case_id == tc1.id))).scalars().first()
            cfg1.extract_map_json = json.dumps({"uid": "data.id"})
            await db2.commit()

        calls = []

        def handler(request):
            calls.append(str(request.url))
            if request.method == "POST":
                return httpx.Response(201, json={"data": {"id": 77}})
            assert "/api/users/77" in str(request.url)  # chained var
            return httpx.Response(200, json={"data": {"id": 77}})

        out = await RN.run_api_suite(db, [tc1.id, tc2.id], env.id, None,
                                     _transport(handler), "qa")
        assert out["pass"] == 2 and out["test_run_id"]
        assert len(calls) == 2


@pytest.mark.asyncio
async def test_http_e2e_import_run_bug_coverage():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        spec = {"openapi": "3.0.0", "info": {"title": "T", "version": "9.0"},
                "paths": {"/api/widgets": {"post": {
                    "summary": "Create widget",
                    "responses": {"201": {"description": "c"}, "400": {"description": "b"}}}}}}
        r = await c.post("/api/qa/openapi:import",
                         json={"project_id": "proj-qa3", "content": json.dumps(spec)})
        assert r.status_code == 200, r.text
        assert r.json()["total"] == 1

        r = await c.get("/api/qa/endpoints", params={"project_id": "proj-qa3"})
        assert r.status_code == 200 and len(r.json()) >= 1

        r = await c.post("/api/qa/environments?project_id=proj-qa3",
                         json={"name": "STG", "base_url": "https://stg", "is_default": True})
        assert r.status_code == 200, r.text
        env_id = r.json()["id"]
        r = await c.post(f"/api/qa/environments/{env_id}/secrets",
                         json={"key": "AUTH_TOKEN", "value": "tok123"})
        assert r.status_code == 200 and "tok123" not in r.text
        assert r.json()["secret_keys"] == ["AUTH_TOKEN"]

        r = await c.get("/api/qa/coverage/api", params={"project_id": "proj-qa3"})
        assert r.status_code == 200
        assert any("No Test" in e["gaps"] for e in r.json())

        r = await c.get("/api/qa/test-data:preview", params={"kind": "email"})
        assert r.status_code == 200 and "@example.com" in r.json()["value"]
