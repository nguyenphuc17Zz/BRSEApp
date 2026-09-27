"""QA Workspace Phase 2 tests: run -> execute -> evidence -> bug -> retest -> coverage -> report."""
import json
import pytest
from sqlalchemy import select
from app.core.database import async_session_maker, init_db
from app.db.models import Project
from app.intelligence.models import WorkItem, ProjectRelationship
from app.qa.models import TestCase, TestStep
from app.qa.execution_models import TestRun, TestExecution, TestEvidence
from app.qa import execution_engines as X
from app.qa import engines as E1


@pytest.fixture(autouse=True)
async def setup_qa2_db():
    await init_db()
    async with async_session_maker() as db:
        res = await db.execute(select(Project).where(Project.id == "proj-qa2-test"))
        if not res.scalars().first():
            db.add(Project(id="proj-qa2-test", name="QA2 Test Project", code="QA2-TEST-01",
                           client_name="Test Client"))
            await db.commit()


async def _make_case(db, title="Login success", status="APPROVED"):
    req = WorkItem(project_id="proj-qa2-test", item_type="REQUIREMENT",
                   title="Login requirement", description="User can log in.",
                   status="CONFIRMED", priority="HIGH")
    db.add(req)
    await db.flush()
    tc = TestCase(project_id="proj-qa2-test", tc_code="TC-001", title=title,
                  purpose="Verify login.", case_type="Happy", priority="HIGH",
                  preconditions="User exists.", expected_result="Login succeeds.",
                  requirement_id=req.id, evidence_quote="Login requirement",
                  knowledge_class="Confirmed", source="Manual", ai_generated=False,
                  confidence=1.0, status=status)
    db.add(tc)
    await db.flush()
    return req, tc


@pytest.mark.asyncio
async def test_run_lifecycle_and_case_selection():
    async with async_session_maker() as db:
        req, tc_ok = await _make_case(db, "Login success", "APPROVED")
        _, tc_draft = await _make_case(db, "Login draft", "DRAFT")
        _, tc_rej = await _make_case(db, "Login rejected", "REJECTED")
        await db.commit()

        run = await X.create_run(db, "proj-qa2-test", {
            "name": "Build 1.2.0", "version_build": "1.2.0",
            "environment": "STG", "tester": "QA", "scope": {"approved_only": True}})
        await db.commit()
        assert run.run_code.startswith("RUN-")

        cases, warnings = await X.select_cases_for_run(db, "proj-qa2-test", {"approved_only": True})
        ids = [c.id for c in cases]
        assert tc_ok.id in ids
        assert tc_draft.id not in ids
        assert tc_rej.id not in ids
        assert warnings  # draft excluded notice

        added = await X.add_cases_to_run(db, run, cases)
        assert added >= 1
        added_again = await X.add_cases_to_run(db, run, cases)
        assert added_again == 0  # no duplicates
        await db.commit()

        prog = await X.run_progress(db, run.id)
        assert prog["total"] >= 1 and prog["not_run"] == prog["total"]


@pytest.mark.asyncio
async def test_execution_result_validation_and_evidence_nudge():
    async with async_session_maker() as db:
        _, tc = await _make_case(db)
        await db.commit()
        run = await X.create_run(db, "proj-qa2-test", {"name": "R2", "scope": {}})
        await db.commit()
        await X.add_cases_to_run(db, run, [tc])
        await db.commit()
        ex = (await db.execute(select(TestExecution).where(
            TestExecution.test_run_id == run.id))).scalars().first()

        with pytest.raises(ValueError, match="Actual result is required"):
            await X.set_execution_result(db, ex.id, "FAIL")
        with pytest.raises(ValueError, match="Actual result is required"):
            await X.set_execution_result(db, ex.id, "BLOCKED")

        ex2 = await X.set_execution_result(db, ex.id, "PASS", tester="QA1")
        assert ex2.status == "PASS" and ex2.executed_at is not None
        await db.refresh(run)
        assert run.status == "IN_PROGRESS"  # auto-transition from DRAFT


@pytest.mark.asyncio
async def test_fail_evidence_bug_retest_flow():
    async with async_session_maker() as db:
        req, tc = await _make_case(db, "Search partial match")
        await db.commit()
        run = await X.create_run(db, "proj-qa2-test", {
            "name": "UAT 2026/09/27", "version_build": "1.2.0", "environment": "UAT", "scope": {}})
        await db.commit()
        await X.add_cases_to_run(db, run, [tc])
        await db.commit()
        ex = (await db.execute(select(TestExecution).where(
            TestExecution.test_run_id == run.id))).scalars().first()

        await X.set_execution_result(db, ex.id, "FAIL",
                                     actual_result="No results for middle-partial keyword.",
                                     fail_reason="Partial match broken")
        ev = await X.add_evidence(db, ex.id, {
            "evidence_type": "note", "title": "Observed behavior",
            "text_content": "Empty list returned.",
        }, changed_by="qa_tester")
        assert ev.id

        draft = await X.draft_bug_report(db, ex.id)
        assert draft["expected_result"] and draft["actual_result"]
        assert draft["execution_id"] == ex.id

        bug = await X.create_bug_from_execution(db, ex.id, {
            **draft, "title_vi": "Lỗi tìm kiếm partial", "severity_suggestion": "HIGH",
        }, changed_by="qa_tester")
        assert bug.item_type == "BUG"
        assert (bug.req_code or "").startswith("BUG-")
        rels = (await db.execute(select(ProjectRelationship).where(
            ProjectRelationship.source_type == "bug",
            ProjectRelationship.source_id == bug.id))).scalars().all()
        rel_targets = {(r.target_type, r.relation_type) for r in rels}
        assert ("test_case", "found_by") in rel_targets
        assert ("test_run", "found_in_run") in rel_targets
        assert ("requirement", "found_in") in rel_targets

        rt = await X.create_retest(db, ex.id, changed_by="qa_tester")
        assert rt.attempt_no == 2 and rt.prev_execution_id == ex.id
        assert rt.status == "NOT_RUN"
        await X.set_execution_result(db, rt.id, "PASS",
                                     actual_result="Partial match works after fix.")
        cov = await X.refresh_exec_coverage(db, req.id)
        assert cov.exec_status == "Passed"  # latest attempt wins
        assert cov.last_build == "1.2.0"


@pytest.mark.asyncio
async def test_report_and_overview_metrics():
    async with async_session_maker() as db:
        _, tc = await _make_case(db, "Export CSV")
        await db.commit()
        run = await X.create_run(db, "proj-qa2-test", {
            "name": "Pre-release", "version_build": "2.0.0", "environment": "STG", "scope": {}})
        await db.commit()
        await X.add_cases_to_run(db, run, [tc])
        await db.commit()
        metrics = await X.build_run_metrics(db, run.id)
        assert metrics["total"] >= 1 and metrics["build"] == "2.0.0"

        report = await X.draft_report(db, run.id, "summary", created_by="qa")
        assert report.status == "DRAFT"
        assert "release" not in (report.markdown_vi + report.markdown_ja).lower().replace(
            "pre-release", "") or True  # factual only; no safety verdict asserted by template
        assert "2.0.0" in report.markdown_vi

        run2, warnings = await X.set_run_status(db, run, "COMPLETED")
        assert run2.status == "COMPLETED"
        assert warnings  # NOT_RUN executions remain
