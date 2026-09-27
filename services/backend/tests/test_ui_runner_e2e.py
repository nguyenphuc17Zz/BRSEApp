"""Phase 4 live tests: real headless Chromium against a fixture page.

Covers: generate fallback offline, approve gate, background PASS run with
screenshot evidence, FAIL run with failed_step + trace, bug draft block.
"""
import asyncio
import json
import tempfile
from pathlib import Path

import pytest
import httpx
from sqlalchemy import select
from app.core.database import async_session_maker, init_db
from app.db.models import Project
from app.intelligence.models import WorkItem
from app.qa.models import TestCase, TestStep
from app.qa.api_models import APIEnvironment
from app.qa.ui_models import UIAutomationScript, UIElementMapping, UIPageKnowledge
from app.qa.execution_models import TestEvidence
from app.qa.ui_testing import script_generator as SG
from app.qa.ui_testing import playwright_runner as PR
from app.main import app

LOGIN_HTML = """<!doctype html><html><body>
<form onsubmit="return doLogin(event)">
<label>Email<input id="email" name="email"></label>
<label>Password<input id="password" type="password" name="password"></label>
<button type="submit">Login</button>
</form><p id="msg"></p>
<script>
function doLogin(e){e.preventDefault();
var m=document.getElementById('msg');
m.textContent = document.getElementById('password').value==='correct' ? 'Welcome back' : 'Invalid credentials';
return false;}
</script></body></html>"""


@pytest.fixture(autouse=True)
async def setup_ui_db():
    await init_db()
    async with async_session_maker() as db:
        if not (await db.execute(select(Project).where(Project.id == "proj-qa4"))).scalars().first():
            db.add(Project(id="proj-qa4", name="QA4 UI", code="QA4-01"))
            await db.commit()


async def _seed(db, title="UI login wrong password"):
    req = WorkItem(project_id="proj-qa4", item_type="REQUIREMENT",
                   title="Login UI req", description="Login shows error on bad password.",
                   status="CONFIRMED")
    db.add(req)
    await db.flush()
    env = APIEnvironment(project_id="proj-qa4", name="STG",
                         base_url="https://ui.example.com",
                         variables_json=json.dumps({"TEST_USER": "qa@example.com",
                                                    "TEST_PASSWORD": "wrong"}))
    db.add(env)
    await db.flush()
    tc = TestCase(project_id="proj-qa4", tc_code="TC-U1", title=title,
                  purpose="p", case_type="Negative", priority="HIGH",
                  preconditions="User exists.",
                  expected_result="Error message displayed.",
                  requirement_id=req.id, evidence_quote="q",
                  knowledge_class="Confirmed", source="Manual",
                  ai_generated=False, confidence=1.0, status="APPROVED")
    db.add(tc)
    await db.flush()
    db.add(TestStep(test_case_id=tc.id, step_order=1, action="Open login",
                    expected="Login form visible"))
    db.add(TestStep(test_case_id=tc.id, step_order=2, action="Enter wrong password and submit",
                    expected="Error message displayed"))
    m1 = UIElementMapping(project_id="proj-qa4", page_name="Login Page",
                          element_name="Email Field",
                          locator_json=json.dumps({"strategy": "label", "value": "Email"}))
    m2 = UIElementMapping(project_id="proj-qa4", page_name="Login Page",
                          element_name="Password Field",
                          locator_json=json.dumps({"strategy": "label", "value": "Password"}))
    m3 = UIElementMapping(project_id="proj-qa4", page_name="Login Page",
                          element_name="Login Button",
                          locator_json=json.dumps({"strategy": "role", "value": "button",
                                                   "options": {"name": "Login"}}))
    m4 = UIElementMapping(project_id="proj-qa4", page_name="Login Page",
                          element_name="Error Message",
                          locator_json=json.dumps({"strategy": "text", "value": "Invalid credentials"}))
    db.add_all([m1, m2, m3, m4])
    db.add(UIPageKnowledge(project_id="proj-qa4", page_name="Login Page",
                           url_path="/login", description="Login screen"))
    await db.commit()
    return req, env, tc, [m1, m2, m3, m4]


def _fixture_url() -> str:
    path = Path(tempfile.gettempdir()) / "qa4_login_fixture.html"
    path.write_text(LOGIN_HTML, encoding="utf-8")
    return path.as_uri()


async def _wait_done(db, execution_id: str, timeout_s: int = 90):
    for _ in range(timeout_s * 2):
        st = await PR.get_ui_status(db, execution_id)
        if st["status"] in ("PASS", "FAIL", "BLOCKED", "SKIPPED"):
            return st
        await asyncio.sleep(0.5)
    raise TimeoutError("UI job did not finish in time")


@pytest.mark.asyncio
async def test_generate_approve_gate_and_live_pass_run():
    async with async_session_maker() as db:
        _, env, tc, maps = await _seed(db)
        out = await SG.generate_ui_flow(db, tc.id, changed_by="qa")
        assert out["version"] == 1 and out["status"] == "REVIEW_REQUIRED"
        # approve gate: running before APPROVED must fail
        with pytest.raises(ValueError, match="review and approve"):
            await PR.start_ui_run(db, tc.id, env.id)
        # craft a passing flow manually (human review simulation)
        url = _fixture_url()
        env.variables_json = json.dumps({"TEST_USER": "qa@example.com",
                                         "TEST_PASSWORD": "correct",
                                         "WEB_BASE_URL": url.rsplit("/", 1)[0] or url})
        await db.commit()
        script = (await db.execute(select(UIAutomationScript).where(
            UIAutomationScript.test_case_id == tc.id))).scalars().first()
        by_name = {m.element_name: m.id for m in maps}
        script.flow_json = json.dumps([
            {"order": 1, "label": "Open Login", "action": "open", "value": url},
            {"order": 2, "label": "Enter email", "action": "fill",
             "mapping_id": by_name["Email Field"], "value": "{{TEST_USER}}"},
            {"order": 3, "label": "Enter password", "action": "fill",
             "mapping_id": by_name["Password Field"], "value": "{{TEST_PASSWORD}}"},
            {"order": 4, "label": "Click Login", "action": "click",
             "mapping_id": by_name["Login Button"]},
            {"order": 5, "label": "See welcome", "action": "verify_text",
             "target": {"strategy": "text", "value": "Welcome back"},
             "value": "Welcome back", "assertion_source": "expected"},
        ])
        script.status = "APPROVED"
        script.updated_by = "qa"
        await db.commit()

        started = await PR.start_ui_run(db, tc.id, env.id, changed_by="qa")
        assert started["status"] == "RUNNING"
        # polling works while running
        st0 = await PR.get_ui_status(db, started["execution_id"])
        assert st0["status"] in ("RUNNING", "PASS", "FAIL")
        final = await _wait_done(db, started["execution_id"])
        assert final["status"] == "PASS", final.get("fail_reason")
        ev = (await db.execute(select(TestEvidence).where(
            TestEvidence.execution_id == started["execution_id"]))).scalars().all()
        assert any(e.evidence_type == "screenshot" and e.file_path for e in ev)


@pytest.mark.asyncio
async def test_live_fail_run_captures_step_screenshot_trace():
    async with async_session_maker() as db:
        _, env, tc, maps = await _seed(db)
        url = _fixture_url()
        env.variables_json = json.dumps({"WEB_BASE_URL": url.rsplit("/", 1)[0] or url})
        await db.commit()
        by_name = {m.element_name: m.id for m in maps}
        script = UIAutomationScript(
            test_case_id=tc.id,
            flow_json=json.dumps([
                {"order": 1, "label": "Open Login", "action": "open", "value": url},
                {"order": 2, "label": "See dashboard", "action": "verify_text",
                 "target": {"strategy": "text", "value": "Dashboard loaded"},
                 "value": "Dashboard loaded", "assertion_source": "expected"},
            ]),
            script_text="display only", script_version=1, status="APPROVED",
            updated_by="qa")
        db.add(script)
        await db.commit()
        started = await PR.start_ui_run(db, tc.id, env.id, changed_by="qa")
        final = await _wait_done(db, started["execution_id"])
        assert final["status"] == "FAIL"
        doc = json.loads(final["actual_result"])
        assert doc["failed_step"]["order"] == 2
        assert doc["error_class"] in ("Timeout", "Possible Application Bug", "Unknown")
        ev = (await db.execute(select(TestEvidence).where(
            TestEvidence.execution_id == started["execution_id"]))).scalars().all()
        kinds = {e.evidence_type for e in ev}
        assert "screenshot" in kinds
        assert any(e.title.startswith("Playwright trace") for e in ev)


@pytest.mark.asyncio
async def test_http_ui_endpoints():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/qa/overview/ui", params={"project_id": "proj-qa4"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "automated" in body and "recent_failures" in body
        r = await c.get("/api/qa/coverage/ui", params={"project_id": "proj-qa4"})
        assert r.status_code == 200
        r = await c.get("/api/qa/ui-candidates", params={"project_id": "proj-qa4"})
        assert r.status_code == 200
