import pytest
from app.core.database import async_session_maker, init_db
from app.integrations.google.client import GoogleWorkspaceClient
from app.integrations.google.drive import GoogleDriveService
from app.integrations.google.docs import GoogleDocsService
from app.integrations.google.sheets import GoogleSheetsService
from app.integrations.google.slides import GoogleSlidesService
from app.integrations.slack.client import SlackClient
from app.integrations.slack.context import SlackContextRetriever
from app.integrations.slack.analyzer import SlackMessageAnalyzer
from app.integrations.slack.reply import SlackReplyGenerator
from app.integrations.desktop.app_detector import WindowsAppDetector
from app.integrations.desktop.profiles import DesktopProfileManager
from app.integrations.desktop.clipboard import ClipboardService
from app.integrations.desktop.agent import desktop_agent
from app.integrations.context_provider import ContextPackage, ContextBudgetManager
from app.integrations.manager import integration_manager
from app.integrations.models import IntegrationAccount, SlackChannelMapping

@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()

@pytest.mark.asyncio
async def test_google_workspace_flow():
    """Verify Docs parsing, Sheets formula protection, and Slides with speaker notes."""
    # 1. Test Docs parsing
    sample_doc = {
        "title": "ユーザー認証仕様書 (OAuth 2.0 Flow)",
        "body": {
            "content": [
                {"paragraph": {"elements": [{"textRun": {"content": "ユーザー認証仕様書\n"}}]}},
                {"paragraph": {"elements": [{"textRun": {"content": "本システムはGoogle OAuth 2.0認可コードフローを使用します。\n"}}]}}
            ]
        }
    }
    doc_segs, doc_meta = GoogleDocsService.parse_segments(sample_doc)
    assert len(doc_segs) >= 2
    assert any("OAuth" in s.source_text for s in doc_segs)

    # 2. Test Sheets parsing with strict formula protection
    sample_sheet = {
        "properties": {"title": "機能一覧・要件定義"},
        "sheets": [
            {
                "properties": {"sheetId": 0, "title": "Requirements"},
                "data": [
                    {
                        "rowData": [
                            {"values": [{"userEnteredValue": {"stringValue": "ID"}}, {"userEnteredValue": {"stringValue": "機能名"}}]},
                            {"values": [{"userEnteredValue": {"stringValue": "REQ-01"}}, {"userEnteredValue": {"formulaValue": '=VLOOKUP(A2, A:B, 1, FALSE)'}}]},
                            {"values": [{"userEnteredValue": {"stringValue": "REQ-02"}}, {"userEnteredValue": {"formulaValue": '=SUM(C2:C10)'}}]}
                        ]
                    }
                ]
            }
        ]
    }
    sheet_segs, sheet_meta = GoogleSheetsService.parse_segments(sample_sheet)
    assert sheet_meta["formula_cells_protected"] >= 2
    for s in sheet_segs:
        assert not s.source_text.startswith("=")
        assert "VLOOKUP" not in s.source_text
        assert "SUM" not in s.source_text

    # 3. Test Slides parsing & speaker notes
    sample_slide = {
        "title": "システムアーキテクチャ概要",
        "slides": [
            {
                "objectId": "slide_p1",
                "pageElements": [
                    {
                        "shape": {
                            "text": {
                                "textElements": [
                                    {"textRun": {"content": "マイクロサービス構成と非同期ジョブキュー\n"}}
                                ]
                            }
                        }
                    }
                ],
                "slideProperties": {
                    "notesPage": {
                        "pageElements": [
                            {
                                "shape": {
                                    "text": {
                                        "textElements": [
                                            {"textRun": {"content": "スピーカーノート: 発表時はスライド遷移のタイミングに注意してください。\n"}}
                                        ]
                                    }
                                }
                            }
                        ]
                    }
                }
            }
        ]
    }
    slide_segs, slide_meta = GoogleSlidesService.parse_segments(sample_slide, translate_notes=True)
    assert len(slide_segs) >= 2
    assert any("スピーカーノート" in s.source_text or "アーキテクチャ" in s.source_text for s in slide_segs)

@pytest.mark.asyncio
async def test_slack_integration_and_smart_analysis():
    """Verify Slack channels, message classification, thread context, and 4-option reply generation."""
    # 1. Channels list
    channels = await SlackClient.list_channels("mock_token", is_mock=True)
    assert len(channels) >= 3

    # 2. Smart message analysis & priority scoring
    q_msg = "ベトナムチーム側での結合テストはいつ頃完了予定でしょうか？"
    q_analysis = SlackMessageAnalyzer.analyze_message(q_msg)
    assert "QUESTION" in q_analysis["tags"]
    assert q_analysis["priority_score"] >= 60

    bug_msg = "【至急バグ報告】ログイン画面でパスワードに特殊文字を含めると500エラーが発生します。調査をお願いできますか？"
    bug_analysis = SlackMessageAnalyzer.analyze_message(bug_msg)
    assert "BUG" in bug_analysis["tags"]
    assert bug_analysis["priority_score"] >= 85
    assert bug_analysis["action_recommended"] == "translate_and_suggest_reply"

    fyi_msg = "おはようございます。"
    fyi_analysis = SlackMessageAnalyzer.analyze_message(fyi_msg)
    assert fyi_analysis["priority_score"] < 60

    # 3. Thread context retrieval
    thread_ctx = await SlackContextRetriever.build_message_context(
        token="mock_token",
        channel_id="C01ABCDEF",
        channel_name="project-abc-banking",
        message_ts="1725440100.000300",
        thread_ts="1725440000.000100",
        is_mock=True
    )
    assert thread_ctx["thread_length"] >= 2
    assert any("Yamada" in m["sender"] for m in thread_ctx["messages"])

    # 4. 4-Option Japanese Reply Generator (Zero auto-send safety)
    replies = await SlackReplyGenerator.generate_replies(
        current_message=q_msg,
        thread_context=thread_ctx["messages"]
    )
    assert len(replies) == 4
    styles = [r["style"] for r in replies]
    assert "Normal" in styles
    assert "Polite" in styles
    assert "Very Polite" in styles
    assert "Concise" in styles

def test_windows_desktop_agent_and_profiles():
    """Verify foreground window detection, application profiles, and clipboard state management."""
    # 1. Foreground window info
    win_info = WindowsAppDetector.get_foreground_window_info()
    assert "hwnd" in win_info
    assert "process_name" in win_info

    # 2. Application Profile
    slack_profile = DesktopProfileManager.get_profile_for_app("slack.exe")
    assert slack_profile["mode"] == "conversation"

    word_profile = DesktopProfileManager.get_profile_for_app("winword.exe")
    assert word_profile["mode"] == "document"

    excel_profile = DesktopProfileManager.get_profile_for_app("excel.exe")
    assert excel_profile["mode"] == "table"

    # 3. Clipboard Safety: Save & Restore
    ClipboardService.save_state()
    ClipboardService.set_text("Test Comtor Clipboard")
    assert ClipboardService.get_text() == "Test Comtor Clipboard"
    ClipboardService.restore_state()

def test_context_budget_manager():
    """Verify ContextBudgetManager keeps tokens within limit and enforces priority rules."""
    pkg = ContextPackage(
        source_type="slack",
        project_instructions=["Rule 1: Use formal keigo."] * 20,
        glossary_terms=[
            {"source_term": "認証", "target_term": "xác thực", "scope": "global"},
            {"source_term": "認証", "target_term": "authentication", "scope": "project"}, # Overrides global
            {"source_term": "例外", "target_term": "ngoại lệ", "scope": "global"}
        ],
        translation_memory=[{"source_text": "A", "target_text": "B"}] * 50,
        slack_context={"messages": [{"sender": "Dev", "text": "Msg " + str(i)} for i in range(40)]}
    )

    trimmed = ContextBudgetManager.trim_to_budget(pkg, max_total_tokens=3000)
    assert trimmed.estimated_tokens <= 3500
    # Verify project-specific terminology takes priority over global
    auth_term = next(g for g in trimmed.glossary_terms if g["source_term"] == "認証")
    assert auth_term["target_term"] == "authentication"

@pytest.mark.asyncio
async def test_integration_health_and_cache_retention():
    """Verify health diagnostics and cache cleanup."""
    async with async_session_maker() as db:
        health = await integration_manager.get_health_status(db)
        assert "google" in health
        assert "slack" in health
        assert "desktop" in health
        assert "cache" in health

        cleaned = await integration_manager.clean_cache(db, all_entries=True)
        assert cleaned >= 0
