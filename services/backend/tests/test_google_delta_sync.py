import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, delete

from app.main import app
from app.core.database import async_session_maker, init_db
from app.documents.models import DocumentJob, DocumentSegment, DocumentFile
from app.integrations.models import IntegrationAccount
from app.db.models import TranslationMemory
from app.integrations.google.google_jobs import google_job_manager
from app.integrations.google.drive import GoogleDriveService
from app.integrations.google.sheets import GoogleSheetsService
from app.integrations.google.client import GoogleWorkspaceClient

SAMPLE_SHEET = {
    "properties": {"title": "Test Delta Sheet"},
    "sheets": [
        {
            "properties": {"sheetId": 0, "title": "Sheet1"},
            "data": [
                {
                    "rowData": [
                        {"values": [{"userEnteredValue": {"stringValue": "こんにちは"}}]},
                        {"values": [{"userEnteredValue": {"stringValue": "新しいテキスト"}}]}
                    ]
                }
            ]
        }
    ]
}

@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    yield
    async with async_session_maker() as db:
        await db.execute(delete(IntegrationAccount).where(IntegrationAccount.provider == "google"))
        await db.commit()

@pytest.mark.asyncio
async def test_existing_translation_endpoint_and_delta_sync():
    """Verifies existing translation lookup and in-place sync execution."""
    async with async_session_maker() as db:
        acc = IntegrationAccount(
            provider="google",
            account_name="Delta Workspace",
            email="delta@google.com",
            encrypted_access_token="mock_token",
            is_active=True,
            is_mock=True
        )
        db.add(acc)

        doc_file = DocumentFile(
            filename="Test_Delta_File",
            file_type="gsheet",
            file_size=2048,
            original_path="drive-file-orig-123",
            detected_language="ja"
        )
        db.add(doc_file)
        await db.commit()
        await db.refresh(doc_file)

        prev_job = DocumentJob(
            document_id=doc_file.id,
            status="completed",
            source_language="ja",
            target_language="vi",
            provider="gemini",
            model="gemini-3.7-flash",
            output_filename="Test_Delta_File_VI",
            output_path="https://drive.google.com/open?id=existing-copy-target-999",
            completed_segments=5,
            total_segments=5
        )
        db.add(prev_job)

        # Add TM entry for 'こんにちは' -> 'Xin chào'
        tm = TranslationMemory(
            source_text="こんにちは",
            target_text="Xin chào",
            source_language="ja",
            target_language="vi",
            provider="gemini"
        )
        db.add(tm)
        await db.commit()

    # 1. Test existing translation endpoint
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/integrations/google/drive/files/drive-file-orig-123/existing-translation?target_language=vi")
        assert res.status_code == 200
        data = res.json()
        assert data["found"] is True
        assert data["target_file_id"] == "existing-copy-target-999"
        assert "existing-copy-target-999" in data["web_url"]

        # 1b. Test that trashed file on Drive is ignored
        with patch.object(GoogleDriveService, "get_file_metadata", new_callable=AsyncMock, return_value={"id": "existing-copy-target-999", "trashed": True}):
            res_trashed = await ac.get("/api/integrations/google/drive/files/drive-file-orig-123/existing-translation?target_language=vi")
            assert res_trashed.status_code == 200
            assert res_trashed.json()["found"] is False

    # 2. Setup job for In-Place Sync
    async with async_session_maker() as db:
        sync_job = DocumentJob(
            document_id=doc_file.id,
            status="queued",
            source_language="ja",
            target_language="vi",
            provider="gemini",
            model="gemini-3.7-flash",
            style="Technical",
            options_json='{"file_id": "drive-file-orig-123", "file_type": "gsheet", "title": "Test_Delta_File", "target_mode": "update", "target_file_id": "existing-copy-target-999", "translate_sheet_names": false}'
        )
        db.add(sync_job)
        await db.commit()
        await db.refresh(sync_job)
        new_job_id = sync_job.id

    applied_copy_ids = []

    async def fake_apply_translations(access_token, copy_spreadsheet_id, updates, is_mock=False):
        applied_copy_ids.append(copy_spreadsheet_id)
        return True

    async def fake_translate_batch(*args, **kwargs):
        batch = kwargs.get("batch") or []
        for seg in batch:
            seg.translated_text = f"{seg.source_text} (VI)"
            seg.status = "translated"

    create_copy_mock = AsyncMock()

    with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="fake_access_token"), \
         patch.object(GoogleSheetsService, "get_spreadsheet", new_callable=AsyncMock, return_value=SAMPLE_SHEET), \
         patch.object(GoogleDriveService, "create_translated_copy", create_copy_mock), \
         patch.object(GoogleSheetsService, "apply_translations_to_copy", side_effect=fake_apply_translations), \
         patch.object(google_job_manager, "_translate_batch", side_effect=fake_translate_batch):

        # Execute pipeline
        await google_job_manager._run_job_pipeline(new_job_id)

    # Verify:
    # 1. create_translated_copy was NOT called (in-place update)
    assert create_copy_mock.call_count == 0

    # 2. apply_translations_to_copy was called directly on existing-copy-target-999
    assert "existing-copy-target-999" in applied_copy_ids

    async with async_session_maker() as db:
        finished_job = (await db.execute(select(DocumentJob).where(DocumentJob.id == new_job_id))).scalar_one()
        assert finished_job.status in ("completed", "partially_completed")

        # Check segments
        segs = (await db.execute(select(DocumentSegment).where(DocumentSegment.job_id == new_job_id))).scalars().all()
        assert len(segs) == 2
        
        # Segment 0 ("こんにちは") must have been matched from TM
        seg_tm = next(s for s in segs if s.source_text == "こんにちは")
        assert seg_tm.status == "translated"
        assert seg_tm.translated_text == "Xin chào"
        assert seg_tm.context_hint == "TM_EXACT_MATCH"

        # Segment 1 ("新しいテキスト") must have been translated by AI / fake_translate_batch
        seg_ai = next(s for s in segs if s.source_text == "新しいテキスト")
        assert seg_ai.status == "translated"
        assert seg_ai.translated_text == "新しいテキスト (VI)"


@pytest.mark.asyncio
async def test_google_docs_smart_delta_sync():
    """Verifies that Google Docs In-Place Sync cleans up deleted segments and inserts new segments via insertText."""
    from app.integrations.google.docs import GoogleDocsService
    
    # Target doc content mock: has Segment A translated and Segment B translated
    target_doc_mock = {
        "title": "Target Doc",
        "tabs": [
            {
                "tabProperties": {"tabId": "t.0", "title": "Tab 1"},
                "documentTab": {
                    "body": {
                        "content": [
                            {"paragraph": {"elements": [{"textRun": {"content": "Xin chào thế giới\n"}}]}},
                            {"paragraph": {"elements": [{"textRun": {"content": "Giao diện React cũ\n"}}]}},
                            {"startIndex": 50, "endIndex": 51}
                        ]
                    }
                }
            }
        ]
    }

    # Previous job segments: Segment A and Segment B
    prev_seg_a = DocumentSegment(
        id="s1",
        job_id="j1",
        segment_index=0,
        location_json='{"tab_id": "t.0"}',
        source_text="Hello world",
        translated_text="Xin chào thế giới"
    )
    prev_seg_b = DocumentSegment(
        id="s2",
        job_id="j1",
        segment_index=1,
        location_json='{"tab_id": "t.0"}',
        source_text="Old React Client",
        translated_text="Giao diện React cũ"
    )

    # Current job segments: Segment A remains, Segment B deleted, Segment C newly added
    curr_seg_a = DocumentSegment(
        id="s3",
        job_id="j2",
        segment_index=0,
        location_json='{"tab_id": "t.0"}',
        source_text="Hello world",
        translated_text="Xin chào thế giới"
    )
    curr_seg_c = DocumentSegment(
        id="s4",
        job_id="j2",
        segment_index=1,
        location_json='{"tab_id": "t.0"}',
        source_text="New Cloud Monitoring",
        translated_text="Hệ thống giám sát Cloud mới"
    )

    sent_requests = []
    async def fake_batch_update(token, doc_id, requests):
        sent_requests.extend(requests)
        return True

    with patch.object(GoogleDocsService, "get_document_content", new_callable=AsyncMock, return_value=target_doc_mock):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"replies": []}

            await GoogleDocsService.apply_smart_delta_sync_to_existing_doc(
                access_token="fake_token",
                target_document_id="target-doc-999",
                segments=[curr_seg_a, curr_seg_c],
                previous_segments=[prev_seg_a, prev_seg_b],
                is_mock=False
            )

            # Inspect calls to batchUpdate
            assert mock_post.called
            all_batches = [call.kwargs.get("json", {}).get("requests", []) for call in mock_post.call_args_list]
            flattened = [r for batch in all_batches for r in batch]

            # 1. Check that deleted segment B ("Giao diện React cũ") was cleared via replaceAllText
            del_req = next((r for r in flattened if "replaceAllText" in r and r["replaceAllText"]["containsText"]["text"] == "Giao diện React cũ"), None)
            assert del_req is not None
            assert del_req["replaceAllText"]["replaceText"] == ""

            # 2. Check that newly added segment C was inserted via insertText
            ins_req = next((r for r in flattened if "insertText" in r), None)
            assert ins_req is not None
            assert "Hệ thống giám sát Cloud mới" in ins_req["insertText"]["text"]
            assert ins_req["insertText"]["location"]["tabId"] == "t.0"


@pytest.mark.asyncio
async def test_google_docs_context_anchored_delta_sync_modified_and_anchors():
    """Verifies that:
    1. Modified segment (e.g. text appended to heading) replaces old translation in-place via replaceAllText.
    2. Segment inserted before title anchors before following segment's startIndex.
    """
    from app.integrations.google.docs import GoogleDocsService

    target_doc_mock = {
        "title": "Target Doc",
        "tabs": [
            {
                "tabProperties": {"tabId": "t.0", "title": "Tab 1"},
                "documentTab": {
                    "body": {
                        "content": [
                            {
                                "startIndex": 1,
                                "endIndex": 25,
                                "paragraph": {"elements": [{"textRun": {"content": "【プロジェクト要件仕様】\n"}}]}
                            },
                            {
                                "startIndex": 25,
                                "endIndex": 60,
                                "paragraph": {"elements": [{"textRun": {"content": "1. システムアーキテクチャの概要\n"}}]}
                            },
                            {"startIndex": 60, "endIndex": 61}
                        ]
                    }
                }
            }
        ]
    }

    # Previous segments
    prev_title = DocumentSegment(
        id="p1",
        job_id="j1",
        segment_index=0,
        location_json='{"tab_id": "t.0"}',
        source_text="ĐẶC TẢ YÊU CẦU DỰ ÁN",
        translated_text="【プロジェクト要件仕様】"
    )
    prev_heading = DocumentSegment(
        id="p2",
        job_id="j1",
        segment_index=1,
        location_json='{"tab_id": "t.0"}',
        source_text="1. TỔNG QUAN KIẾN TRÚC HỆ THỐNG",
        translated_text="1. システムアーキテクチャの概要"
    )

    # Current segments:
    # 1) seg_top: inserted at the very top before prev_title
    seg_top = DocumentSegment(
        id="c0",
        job_id="j2",
        segment_index=0,
        location_json='{"tab_id": "t.0"}',
        source_text="đây là text dùng để test",
        translated_text="これはテスト用テキストです"
    )
    # 2) seg_title: unchanged
    seg_title = DocumentSegment(
        id="c1",
        job_id="j2",
        segment_index=1,
        location_json='{"tab_id": "t.0"}',
        source_text="ĐẶC TẢ YÊU CẦU DỰ ÁN",
        translated_text="【プロジェクト要件仕様】"
    )
    # 3) seg_heading: modified with appended text
    seg_heading = DocumentSegment(
        id="c2",
        job_id="j2",
        segment_index=2,
        location_json='{"tab_id": "t.0"}',
        source_text="1. TỔNG QUAN KIẾN TRÚC HỆ THỐNG đây là text dùng để test",
        translated_text="1. システムアーキテクチャの概要 これはテスト用テキストです"
    )

    with patch.object(GoogleDocsService, "get_document_content", new_callable=AsyncMock, return_value=target_doc_mock):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"replies": []}

            await GoogleDocsService.apply_smart_delta_sync_to_existing_doc(
                access_token="fake_token",
                target_document_id="target-doc-999",
                segments=[seg_top, seg_title, seg_heading],
                previous_segments=[prev_title, prev_heading],
                is_mock=False
            )

            assert mock_post.called
            all_batches = [call.kwargs.get("json", {}).get("requests", []) for call in mock_post.call_args_list]
            flattened = [r for batch in all_batches for r in batch]

            # 1. Check modified segment replacement: replaceAllText old_tgt -> new_tgt
            mod_req = next((
                r for r in flattened
                if "replaceAllText" in r
                and r["replaceAllText"]["containsText"]["text"] == "1. システムアーキテクチャの概要"
            ), None)
            assert mod_req is not None, f"Expected replaceAllText for modified heading, got: {flattened}"
            assert mod_req["replaceAllText"]["replaceText"] == "1. システムアーキテクチャの概要 これはテスト用テキストです"

            # 2. Check context-anchored insertion for seg_top: anchored BEFORE seg_title (startIndex = 1)
            ins_req = next((r for r in flattened if "insertText" in r), None)
            assert ins_req is not None, f"Expected insertText for top-inserted text, got: {flattened}"
            assert "これはテスト用テキストです" in ins_req["insertText"]["text"]
            assert ins_req["insertText"]["location"]["tabId"] == "t.0"
            assert ins_req["insertText"]["location"]["index"] == 1


