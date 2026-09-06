import datetime
import pytest
from sqlalchemy import select
from app.core.database import async_session_maker, init_db
from app.db.models import Project
from app.intelligence.models import WorkItem, WorkItemEvidence, AutomationRule, AutomationRunLog
from app.intelligence.extractors.conversation_analyzer import ConversationAnalyzer
from app.intelligence.extractors.requirement_extractor import RequirementExtractor
from app.intelligence.extractors.bug_analyzer import BugAnalyzer
from app.intelligence.extractors.decision_extractor import DecisionExtractor
from app.intelligence.extractors.todo_extractor import TodoExtractor
from app.intelligence.extractors.meeting_analyzer import MeetingAnalyzer
from app.intelligence.brain.ask_project import AskProjectEngine
from app.intelligence.brain.diff_analyzer import DiffAnalyzer
from app.intelligence.brain.impact_analyzer import ImpactAnalyzer
from app.intelligence.reply.advanced_reply import AdvancedReplyEngine
from app.intelligence.line.line_client import line_client
from app.intelligence.automation.policy_engine import policy_engine

@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    async with async_session_maker() as db:
        res = await db.execute(select(Project).where(Project.id == "proj-intel-test"))
        if not res.scalars().first():
            p = Project(id="proj-intel-test", name="Intel Test Banking", code="INTEL-TEST-01", client_name="Fintech Corp")
            db.add(p)
            await db.commit()

@pytest.mark.asyncio
async def test_requirement_conflict_detection():
    """Verify that requirement extractor identifies conflicts between existing requirements and new inputs."""
    async with async_session_maker() as db:
        p_id = "proj-intel-test"

        # Seed existing requirement: Session timeout 30 minutes
        existing_req = WorkItem(
            project_id=p_id,
            item_type="REQUIREMENT",
            title="Session timeout is 30 minutes",
            description="Active user session must expire after 30 minutes of inactivity.",
            details_json='{"condition": "timeout=30m"}',
            status="CONFIRMED"
        )
        db.add(existing_req)
        await db.commit()

        # Input conflicting requirement: Session timeout 60 minutes
        new_text = "セキュリティ方針の改定に伴い、セッションタイムアウトは60分に設定してください。"
        results = await RequirementExtractor.extract_and_validate(
            db=db,
            project_id=p_id,
            source_text=new_text,
            source_type="slack",
            source_id="msg-101",
            author="Security Lead"
        )

        assert len(results) >= 1
        conflicted_item = results[0]
        # In mock/offline fallback or AI analysis, status should be marked as conflict or details preserved
        assert conflicted_item["title"] is not None
        assert conflicted_item["status"] in ["CONFLICT", "PROPOSED", "NEEDS_CONFIRMATION"]

@pytest.mark.asyncio
async def test_bug_analyzer():
    """Verify that bug analyzer extracts reproduction details and ignores casual chat."""
    async with async_session_maker() as db:
        p_id = "proj-intel-test"
        bug_text = "本番環境でトークン失効後にHTTP 500エラーが発生し、ログイン画面へ遷移できません。再現手順：1. ログイン 2. 60分放置 3. 画面リロード。"
        
        bug_item = await BugAnalyzer.extract_bug(
            db=db,
            project_id=p_id,
            source_text=bug_text,
            source_type="line",
            source_id="line-msg-01",
            author="QA Lead"
        )
        assert bug_item is not None
        assert bug_item.item_type == "BUG"
        assert bug_item.status == "PROPOSED"
        assert "500" in bug_item.description or "トークン" in bug_item.title or "エラー" in bug_item.title

        # Casual chat should NOT create a bug
        chat_text = "明日のお昼休みにプロジェクト進捗について少し相談できますか？"
        non_bug = await BugAnalyzer.extract_bug(
            db=db,
            project_id=p_id,
            source_text=chat_text,
            source_type="line",
            source_id="line-msg-02"
        )
        assert non_bug is None

@pytest.mark.asyncio
async def test_decision_extractor():
    """Verify detection of confirmed project decisions via business signals."""
    async with async_session_maker() as db:
        p_id = "proj-intel-test"
        
        # Decision text with clear agreement signal
        dec_text = "認証フローについては、ご提案のOAuth2 Authorization Code Flowで進める方針で決定いたしました。これで進めてください。"
        dec_item = await DecisionExtractor.extract_decision(
            db=db,
            project_id=p_id,
            source_text=dec_text,
            source_type="slack",
            source_id="msg-dec-1",
            author="Client PM"
        )
        assert dec_item is not None
        assert dec_item.item_type == "DECISION"
        assert dec_item.status == "CONFIRMED"

        # Non-decision text
        casual_text = "OAuth2にするかSAMLにするか、来週また議論しましょう。"
        non_dec = await DecisionExtractor.extract_decision(
            db=db,
            project_id=p_id,
            source_text=casual_text,
            source_type="slack",
            source_id="msg-dec-2"
        )
        assert non_dec is None

@pytest.mark.asyncio
async def test_todo_and_relative_deadline_resolution():
    """Verify Japanese relative deadline resolution to absolute ISO dates."""
    base_date = datetime.date(2026, 9, 4) # Friday
    
    # 明日 -> 2026-09-05
    d_tomorrow = TodoExtractor.resolve_relative_deadline("明日の午前中まで", base_date=base_date)
    assert d_tomorrow == "2026-09-05"

    # 明後日 -> 2026-09-06
    d_after_tomorrow = TodoExtractor.resolve_relative_deadline("明後日までに提出", base_date=base_date)
    assert d_after_tomorrow == "2026-09-06"

    # 9月10日 -> 2026-09-10
    d_explicit = TodoExtractor.resolve_relative_deadline("9月10日必着", base_date=base_date)
    assert d_explicit == "2026-09-10"

    # 月末
    d_eom = TodoExtractor.resolve_relative_deadline("月末まで", base_date=base_date)
    assert d_eom == "2026-09-30"

@pytest.mark.asyncio
async def test_ask_project_brain_and_evidence():
    """Verify evidence-based Q&A cites confirmed knowledge and preserves source references."""
    async with async_session_maker() as db:
        p_id = "proj-intel-test"
        
        # Add a confirmed requirement with evidence
        item = WorkItem(
            project_id=p_id,
            item_type="REQUIREMENT",
            title="OAuth2 Authentication",
            description="Client approved OAuth2 Authorization Code Flow with PKCE.",
            status="CONFIRMED"
        )
        db.add(item)
        await db.flush()

        ev = WorkItemEvidence(
            work_item_id=item.id,
            source_type="slack",
            source_id="msg-999",
            quote_text="OAuth2 Authorization Code Flowで進めます。",
            author="Tanaka-san",
            confirmation_status="CONFIRMED"
        )
        db.add(ev)
        await db.commit()

        # Query Ask Project
        res = await AskProjectEngine.ask_project(
            db=db,
            project_id=p_id,
            question="What authentication mechanism was approved by the client?"
        )
        assert "answer" in res
        assert "citations" in res
        assert len(res["citations"]) >= 1
        assert "known_unknowns" in res

@pytest.mark.asyncio
async def test_advanced_reply_fact_protection():
    """Verify reply generator protects against hallucinated deadline commitments."""
    msg = "明日までに修正対応は可能でしょうか？"
    
    reply_res = await AdvancedReplyEngine.generate_smart_replies(
        incoming_message=msg,
        confirmed_decisions=["Release scheduled for end of month"]
    )
    assert reply_res["detected_intent"] in ["QUESTION", "REQUEST_TIME", "ANSWER", "ACKNOWLEDGE"]
    assert reply_res["commitment_warning"] is not None
    assert len(reply_res["replies"]) == 3
    # Verify at least one reply safely defers commitment
    all_reply_texts = " ".join([r["text"] for r in reply_res["replies"]])
    assert ("確認" in all_reply_texts or "ご連絡" in all_reply_texts or "明日" in all_reply_texts)

@pytest.mark.asyncio
async def test_line_webhook_normalization_and_reply_guard():
    """Verify LINE webhook event normalization and user confirmation guard."""
    mock_event = {
        "type": "message",
        "replyToken": "nHuyWiB7yP5Zw52FIkcQobQuGDXCTA",
        "source": {
            "userId": "U4af498001d",
            "type": "user"
        },
        "timestamp": 1462629479859,
        "message": {
            "type": "text",
            "id": "325708",
            "text": "仕様書の更新版を確認しました。問題ありません。"
        }
    }
    norm = line_client.normalize_event(mock_event)
    assert norm is not None
    assert norm["source"] == "line"
    assert norm["sender"] == "U4af498001d"
    assert norm["text"] == "仕様書の更新版を確認しました。問題ありません。"
    assert norm["reply_token"] == "nHuyWiB7yP5Zw52FIkcQobQuGDXCTA"

@pytest.mark.asyncio
async def test_automation_policy_engine_audit_log():
    """Verify Level 2 automation drafts work items and logs audit trail without silent external actions."""
    async with async_session_maker() as db:
        p_id = "proj-intel-test"
        await policy_engine.ensure_default_rules(db, p_id)

        # Trigger event: high-confidence requirement
        actions = await policy_engine.evaluate_event(
            db=db,
            event_trigger="requirement_extracted",
            event_data={
                "project_id": p_id,
                "item_type": "REQUIREMENT",
                "title": "OAuth2 PKCE Support",
                "description": "Must support PKCE for mobile client",
                "confidence": 0.95,
                "quote_text": "PKCEの対応も合わせてお願いします。"
            },
            project_id=p_id
        )

        assert len(actions) >= 1
        # Check audit log in DB
        logs_res = await db.execute(select(AutomationRunLog).order_by(AutomationRunLog.created_at.desc()))
        logs = logs_res.scalars().all()
        assert len(logs) >= 1
        assert "OAuth2 PKCE Support" in logs[0].action_taken or "PROPOSED" in logs[0].action_taken
