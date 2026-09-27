"""Phase 4 pure-logic tests: locator policy, codegen, flow validation, variables, flaky."""
import pytest
from app.qa.ui_testing import locator_policy as LP


def test_locator_priority_and_forbidden():
    assert LP.locator_expression("role", "button", {"name": "Login"}) == \
        "page.get_by_role('button', name='Login')"
    assert LP.locator_expression("label", "Email") == "page.get_by_label('Email')"
    assert LP.locator_expression("testid", "submit") == "page.get_by_test_id('submit')"
    assert LP.validate_locator("role", "button") == []
    bad = LP.validate_locator("css", "ul > li:nth-child(3) > a")
    assert any("nth-child" in v for v in bad)
    assert LP.validate_locator("xpath", "//html/body/div") != []
    assert LP.validate_locator("magic", "x") != []


def test_flow_validation_rejects_sleep_and_missing_locator():
    ok, problems = LP.validate_flow([
        {"order": 1, "action": "open", "value": "https://x/"},
        {"order": 2, "action": "fill", "target": {"strategy": "label", "value": "Email"}, "value": "a"},
    ])
    assert ok and problems == []
    ok2, problems2 = LP.validate_flow([
        {"order": 1, "action": "wait", "value": "5000"},
        {"order": 2, "action": "click"},
    ])
    assert not ok2 and len(problems2) == 2
    ok3, _ = LP.validate_flow([
        {"order": 1, "action": "click", "selector_required": True, "element_hint": "captcha"},
    ])
    assert ok3


def test_codegen_uses_expect_not_sleep():
    flow = [
        {"order": 1, "label": "Open", "action": "open", "value": "https://x/login"},
        {"order": 2, "label": "Fill", "action": "fill",
         "target": {"strategy": "label", "value": "Email"}, "value": "{{TEST_USER}}"},
        {"order": 3, "label": "Go", "action": "click",
         "target": {"strategy": "role", "value": "button", "options": {"name": "Login"}}},
        {"order": 4, "label": "See error", "action": "verify_text",
         "target": {"strategy": "text", "value": "Invalid"}, "value": "Invalid"},
    ]
    code = LP.render_flow_as_python(flow)
    assert "get_by_label('Email')" in code
    assert "get_by_role('button', name='Login')" in code
    assert "expect(" in code
    assert "waitForTimeout" not in code and "sleep" not in code


@pytest.mark.asyncio
async def test_flaky_detection_logic():
    from sqlalchemy import select
    from app.core.database import async_session_maker, init_db
    from app.db.models import Project
    from app.intelligence.models import WorkItem
    from app.qa.models import TestCase
    from app.qa.execution_models import TestExecution
    from app.qa.ui_testing import failure_analyzer as FA
    await init_db()
    async with async_session_maker() as db:
        if not (await db.execute(select(Project).where(Project.id == "proj-flaky"))).scalars().first():
            db.add(Project(id="proj-flaky", name="F", code="F-01"))
            await db.commit()
        req = WorkItem(project_id="proj-flaky", item_type="REQUIREMENT",
                       title="R", description="d", status="CONFIRMED")
        db.add(req)
        await db.flush()
        tc = TestCase(project_id="proj-flaky", tc_code="TC-F1", title="flaky?",
                      purpose="p", case_type="Happy", requirement_id=req.id,
                      evidence_quote="q", status="APPROVED")
        db.add(tc)
        await db.flush()
        from app.qa.execution_models import TestRun
        run = TestRun(project_id="proj-flaky", run_code="RUN-01", name="F run")
        db.add(run)
        await db.flush()
        for st in ["PASS", "FAIL", "PASS", "FAIL"]:
            db.add(TestExecution(test_run_id=run.id, test_case_id=tc.id,
                                 requirement_id=req.id, status=st))
        await db.commit()
        out = await FA.detect_flaky(db, tc.id)
        assert out["flaky"] and out["label"] == "Potentially Flaky"
        out2 = await FA.detect_flaky(db, "nope")
        assert not out2["flaky"]
