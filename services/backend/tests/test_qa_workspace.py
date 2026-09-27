"""QA Workspace Phase 1 tests: review -> findings -> questions -> AC -> test cases -> coverage."""
import pytest
from sqlalchemy import select
from app.core.database import async_session_maker, init_db
from app.db.models import Project
from app.intelligence.models import WorkItem, WorkItemEvidence
from app.qa.models import QAFinding, QAOpenQuestion, AcceptanceCriterion, TestCase, RequirementCoverage
from app.qa import engines as E


@pytest.fixture(autouse=True)
async def setup_qa_db():
    await init_db()
    async with async_session_maker() as db:
        res = await db.execute(select(Project).where(Project.id == "proj-qa-test"))
        if not res.scalars().first():
            db.add(Project(id="proj-qa-test", name="QA Test Project", code="QA-TEST-01",
                           client_name="Test Client"))
            await db.commit()


async def _make_requirement(db, title="登録ボタンを押すとデータを保存する",
                            description="Nhấn nút Đăng ký thì lưu dữ liệu."):
    item = WorkItem(project_id="proj-qa-test", item_type="REQUIREMENT",
                    title=title, description=description, status="PROPOSED", priority="HIGH")
    db.add(item)
    await db.flush()
    db.add(WorkItemEvidence(work_item_id=item.id, source_type="manual",
                            source_id="user_input", quote_text=title))
    await db.flush()
    return item


@pytest.mark.asyncio
async def test_review_assigns_req_code_and_finds_gaps():
    async with async_session_maker() as db:
        item = await _make_requirement(db)
        await db.commit()
        findings = await E.review_requirement(db, item.id, force=True)
        assert len(findings) >= 1
        for f in findings:
            assert f.evidence_quote, "Evidence-first: every finding must carry evidence"
            assert f.knowledge_class in ("Confirmed", "Inferred", "AISuggested")
        await db.refresh(item)
        assert item.req_code and item.req_code.startswith("REQ-")


@pytest.mark.asyncio
async def test_full_flow_questions_ac_cases_coverage():
    async with async_session_maker() as db:
        item = await _make_requirement(db)
        await db.commit()

        findings = await E.review_requirement(db, item.id, force=True)
        assert findings

        questions = await E.generate_questions(db, item.id)
        assert len(questions) >= 1
        q = questions[0]
        assert q.question_vi and q.finding_id

        # Resolve clarification to unblock coverage
        for f in findings:
            f.status = "RESOLVED"
        for qq in questions:
            qq.status = "ANSWERED"
            qq.answer_text = "Đã xác nhận với khách."
        await db.flush()

        acs = await E.generate_acceptance_criteria(db, item.id)
        assert len(acs) >= 1
        assert acs[0].ac_code.startswith("AC-")
        for a in acs:
            a.status = "APPROVED"
        await db.flush()

        cases = await E.generate_test_cases(db, item.id)
        assert len(cases) >= 1
        tc = cases[0]
        assert tc.tc_code.startswith("TC-")
        assert tc.evidence_quote

        cov = await E.refresh_coverage(db, item.id)
        assert cov.has_review is True
        assert cov.findings_open == 0
        assert cov.status == "Covered"

        # Checklist mode produces quick checklist cases
        checks = await E.generate_test_cases(db, item.id, checklist_mode=True)
        assert len(checks) >= 1


@pytest.mark.asyncio
async def test_coverage_blocked_by_clarification():
    async with async_session_maker() as db:
        item = await _make_requirement(db, title="CSV export chức năng xuất file.",
                                       description="Xuất CSV danh sách user.")
        await db.commit()
        await E.review_requirement(db, item.id, force=True)
        qs = await E.generate_questions(db, item.id)
        assert qs
        cov = await E.refresh_coverage(db, item.id)
        assert cov.status == "BlockedByClarification"


@pytest.mark.asyncio
async def test_human_review_transitions():
    async with async_session_maker() as db:
        item = await _make_requirement(db)
        await db.commit()
        findings = await E.review_requirement(db, item.id, force=True)
        f = findings[0]
        f.status = "IGNORED"
        await db.flush()
        cov = await E.refresh_coverage(db, item.id)
        assert cov.findings_open == max(0, len(findings) - 1)
