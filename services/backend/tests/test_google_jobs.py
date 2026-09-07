import asyncio
import json
from unittest.mock import patch, AsyncMock
import pytest
from app.core.database import async_session_maker, init_db
from app.documents.models import DocumentJob, DocumentSegment, DocumentFile, DocumentIssue
from app.integrations.models import IntegrationAccount
from app.integrations.google.client import GoogleWorkspaceClient
from app.integrations.google.drive import GoogleDriveService
from app.integrations.google.docs import GoogleDocsService
from app.integrations.google.sheets import GoogleSheetsService
from app.integrations.google.slides import GoogleSlidesService
from app.integrations.google.google_jobs import google_job_manager
from sqlalchemy import select

SAMPLE_DOC = {
    "title": "ユーザー認証仕様書 (OAuth 2.0 Flow)",
    "body": {
        "content": [
            {"paragraph": {"elements": [{"textRun": {"content": "ユーザー認証仕様書\n"}}]}},
            {"paragraph": {"elements": [{"textRun": {"content": "本システムはGoogle OAuth 2.0認可コードフローを使用します。\n"}}]}}
        ]
    }
}

SAMPLE_SHEET = {
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

SAMPLE_SLIDE = {
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

from sqlalchemy import select, delete

@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    yield
    async with async_session_maker() as db:
        await db.execute(delete(IntegrationAccount).where(IntegrationAccount.provider == "google"))
        await db.commit()

@pytest.mark.asyncio
async def test_google_services_metadata():
    """Verifies that Google metadata extraction works for Docs, Sheets, and Slides."""
    with patch.object(GoogleDocsService, "get_document_content", new_callable=AsyncMock, return_value=SAMPLE_DOC), \
         patch.object(GoogleSheetsService, "get_spreadsheet", new_callable=AsyncMock, return_value=SAMPLE_SHEET), \
         patch.object(GoogleSlidesService, "get_presentation", new_callable=AsyncMock, return_value=SAMPLE_SLIDE):

        # 1. Docs metadata
        doc_meta = await GoogleDocsService.get_metadata("mock_token", "gdoc-101")
        assert doc_meta["format"] == "gdoc"
        assert doc_meta["total_segments"] >= 2
        assert "ユーザー認証仕様書" in doc_meta["title"]

        # 2. Sheets metadata & tabs
        sheet_meta = await GoogleSheetsService.get_metadata("mock_token", "gsheet-102")
        assert sheet_meta["format"] == "gsheet"
        assert "Requirements" in sheet_meta["sheet_names"]
        assert sheet_meta["formula_cells_protected"] >= 2

        # 3. Slides metadata & notes
        slide_meta = await GoogleSlidesService.get_metadata("mock_token", "gslide-103")
        assert slide_meta["format"] == "gslide"
        assert slide_meta["total_slides"] >= 1
        assert slide_meta["total_segments"] >= 2

@pytest.mark.asyncio
async def test_google_sheets_strict_formula_preservation():
    """Ensures 100% of formula cells are never placed in translatable segments."""
    segments, meta = GoogleSheetsService.parse_segments(SAMPLE_SHEET)

    assert meta["formula_cells_protected"] == 2
    for s in segments:
        assert not s.source_text.startswith("=")
        assert "VLOOKUP" not in s.source_text
        assert "SUM" not in s.source_text

@pytest.mark.asyncio
async def test_google_job_manager_full_pipeline():
    """Runs a full Google Sheets translation job verifying segmenting, batching, QA, and safe copy rendering."""
    async with async_session_maker() as db:
        # Create Google account
        acc = IntegrationAccount(
            provider="google",
            account_name="Test Workspace",
            email="test@google.com",
            encrypted_access_token="mock_token",
            is_active=True,
            is_mock=False
        )
        db.add(acc)

        # Create DocumentFile for gsheet
        doc_file = DocumentFile(
            filename="機能一覧・要件定義",
            file_type="gsheet",
            file_size=1024,
            original_path="gsheet-102",
            detected_language="ja"
        )
        db.add(doc_file)
        await db.commit()
        await db.refresh(doc_file)

        # Create DocumentJob
        job = DocumentJob(
            document_id=doc_file.id,
            status="queued",
            source_language="ja",
            target_language="vi",
            provider="gemini",
            model="gemini-3.7-flash",
            style="Technical",
            options_json='{"file_id": "gsheet-102", "file_type": "gsheet", "title": "機能一覧・要件定義"}'
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        job_id = job.id

    copy_mock_resp = {
        "id": "copy-gsheet-102-translated",
        "name": "機能一覧・要件定義_VI",
        "webViewLink": "https://drive.google.com/file/d/copy-gsheet-102-translated/view"
    }

    async def fake_translate_batch(*args, **kwargs):
        batch = kwargs.get("batch") or []
        for seg in batch:
            seg.translated_text = f"{seg.source_text} (VI)"
            seg.status = "translated"

    with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="fake_access_token"), \
         patch.object(GoogleSheetsService, "get_spreadsheet", new_callable=AsyncMock, return_value=SAMPLE_SHEET), \
         patch.object(GoogleDriveService, "create_translated_copy", new_callable=AsyncMock, return_value=copy_mock_resp), \
         patch.object(GoogleSheetsService, "apply_translations_to_copy", new_callable=AsyncMock, return_value=True), \
         patch.object(google_job_manager, "_translate_batch", side_effect=fake_translate_batch):

        # Execute pipeline
        await google_job_manager._run_job_pipeline(job_id)

    async with async_session_maker() as db:
        updated_job = (await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))).scalar_one()
        assert updated_job.status in ("completed", "partially_completed")
        assert updated_job.total_segments > 0
        assert updated_job.completed_segments > 0
        assert updated_job.output_filename is not None
        assert "drive.google.com" in updated_job.output_path

        segs = (await db.execute(select(DocumentSegment).where(DocumentSegment.job_id == job_id))).scalars().all()
        assert len(segs) == updated_job.total_segments
        for s in segs:
            assert s.translated_text is not None
            assert len(s.translated_text) > 0


@pytest.mark.asyncio
async def test_google_translation_custom_target_filename():
    import json
    async with async_session_maker() as db:
        acc = IntegrationAccount(
            provider="google",
            account_name="Custom Name Test",
            email="customname@gmail.com",
            encrypted_access_token="fake_enc_tok",
            is_active=True,
            is_mock=False
        )
        db.add(acc)
        await db.commit()
        await db.refresh(acc)

        doc = DocumentFile(
            filename="KienTrucHeThong.gdoc",
            file_type="gdoc",
            file_size=0,
            original_path="google_custom_doc_01"
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        options = {
            "file_id": "google_custom_doc_01",
            "file_type": "gdoc",
            "title": "KienTrucHeThong",
            "account_id": acc.id,
            "target_filename": "KienTruc_Chuan_BanGiao_2026"
        }
        job = DocumentJob(
            document_id=doc.id,
            status="queued",
            source_language="ja",
            target_language="vi",
            provider="gemini",
            model="gemini-3.7-flash",
            options_json=json.dumps(options)
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    copy_calls = []
    async def mock_create_copy(token, source_file_id, target_name, parent_folder_id=None, is_mock=False):
        copy_calls.append(target_name)
        return {"id": "copy-custom-id", "name": target_name}

    with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="fake_access_token"), \
         patch.object(GoogleDocsService, "get_document_content", new_callable=AsyncMock, return_value=SAMPLE_DOC), \
         patch.object(GoogleDriveService, "create_translated_copy", side_effect=mock_create_copy), \
         patch.object(GoogleDocsService, "apply_translations_to_copy", new_callable=AsyncMock, return_value=True), \
         patch.object(google_job_manager, "_translate_batch", new_callable=AsyncMock):

        await google_job_manager._run_job_pipeline(job_id)

    assert len(copy_calls) == 1
    assert copy_calls[0] == "KienTruc_Chuan_BanGiao_2026"

    async with async_session_maker() as db:
        updated_job = (await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))).scalar_one()
        assert updated_job.output_filename == "KienTruc_Chuan_BanGiao_2026"

@pytest.mark.asyncio
async def test_google_drive_office_file_auto_routing():
    """Verifies that an Office file (.docx) on Google Drive routes to the hybrid pipeline even when translate_images is False."""
    async with async_session_maker() as db:
        acc = IntegrationAccount(
            provider="google",
            account_name="acc_office_test",
            encrypted_access_token="fake_enc_tok",
            is_active=True,
            is_mock=True
        )
        db.add(acc)
        await db.commit()
        await db.refresh(acc)

        doc = DocumentFile(
            filename="07_HuongDan_KienTruc_Microservices_VI.docx",
            file_type="gdoc",
            file_size=0,
            original_path="google_docx_file_id_101"
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        options = {
            "file_id": "google_docx_file_id_101",
            "file_type": "gdoc",
            "title": "07_HuongDan_KienTruc_Microservices_VI.docx",
            "account_id": acc.id,
            "translate_images": False
        }
        job = DocumentJob(
            document_id=doc.id,
            status="queued",
            source_language="vi",
            target_language="ja",
            provider="gemini",
            model="gemini-3.7-flash",
            options_json=json.dumps(options)
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="fake_token"), \
         patch.object(GoogleDocsService, "get_document_content", new_callable=AsyncMock) as mock_docs_api, \
         patch.object(google_job_manager, "_run_hybrid_image_pipeline", new_callable=AsyncMock) as mock_hybrid_pipe:

        await google_job_manager._run_job_pipeline(job_id)

        # Docs REST API must NOT be called on an Office file
        assert mock_docs_api.call_count == 0
        # Hybrid pipeline must be called
        assert mock_hybrid_pipe.call_count == 1

@pytest.mark.asyncio
async def test_google_drive_office_file_self_healing_fallback():
    """Verifies that if Google Docs API returns an Office file 400 error, the worker self-heals by routing to the hybrid pipeline."""
    async with async_session_maker() as db:
        acc = IntegrationAccount(
            provider="google",
            account_name="acc_fallback_test",
            encrypted_access_token="fake_enc_tok",
            is_active=True,
            is_mock=True
        )
        db.add(acc)
        await db.commit()
        await db.refresh(acc)

        # Filename without extension that was initially treated as a native gdoc
        doc = DocumentFile(
            filename="ArchitectureGuide",
            file_type="gdoc",
            file_size=0,
            original_path="gdoc_with_hidden_office_mime"
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        options = {
            "file_id": "gdoc_with_hidden_office_mime",
            "file_type": "gdoc",
            "title": "ArchitectureGuide",
            "account_id": acc.id,
            "translate_images": False
        }
        job = DocumentJob(
            document_id=doc.id,
            status="queued",
            source_language="vi",
            target_language="ja",
            provider="gemini",
            model="gemini-3.7-flash",
            options_json=json.dumps(options)
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    office_error = ValueError(
        'Failed to fetch Google Doc: { "error": { "code": 400, "message": "This operation is not supported for this document. The document must not be an Office file.", "status": "FAILED_PRECONDITION" } }'
    )

    with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="fake_token"), \
         patch.object(GoogleDocsService, "get_document_content", new_callable=AsyncMock, side_effect=office_error), \
         patch.object(google_job_manager, "_run_hybrid_image_pipeline", new_callable=AsyncMock) as mock_hybrid_pipe:

        await google_job_manager._run_job_pipeline(job_id)

        # When Google Docs API throws the Office file error, hybrid pipeline recovers seamlessly
        assert mock_hybrid_pipe.call_count == 1


@pytest.mark.asyncio
async def test_google_sheet_translate_sheet_names_flag():
    """Verify that translate_sheet_names option triggers translate_and_update_sheet_titles when enabled and skips when disabled."""
    async with async_session_maker() as db:
        acc = IntegrationAccount(
            provider="google",
            account_name="Sheet Title Flag Test",
            email="sheettitle@gmail.com",
            encrypted_access_token="fake_enc_tok",
            is_active=True,
            is_mock=False
        )
        db.add(acc)
        await db.commit()
        await db.refresh(acc)

        doc = DocumentFile(filename="SheetFlag.gsheet", file_type="sheet", file_size=0, original_path="gsheet_flag_01")
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        # 1. Test enabled (default)
        job_enabled = DocumentJob(
            document_id=doc.id,
            status="queued",
            source_language="ja",
            target_language="vi",
            provider="gemini",
            model="gemini-3.7-flash",
            options_json=json.dumps({
                "file_id": "gsheet_flag_01",
                "file_type": "sheet",
                "title": "SheetFlag",
                "account_id": acc.id,
                "translate_sheet_names": True
            })
        )
        # 2. Test disabled
        job_disabled = DocumentJob(
            document_id=doc.id,
            status="queued",
            source_language="ja",
            target_language="vi",
            provider="gemini",
            model="gemini-3.7-flash",
            options_json=json.dumps({
                "file_id": "gsheet_flag_01",
                "file_type": "sheet",
                "title": "SheetFlag",
                "account_id": acc.id,
                "translate_sheet_names": False
            })
        )
        db.add_all([job_enabled, job_disabled])
        await db.commit()
        await db.refresh(job_enabled)
        await db.refresh(job_disabled)

    copy_mock_resp = {
        "id": "copy-gsheet-flag-translated",
        "name": "SheetFlag_VI",
        "webViewLink": "https://drive.google.com/file/d/copy-gsheet-flag-translated/view"
    }

    async def fake_translate_batch(*args, **kwargs):
        batch = kwargs.get("batch") or []
        for seg in batch:
            seg.translated_text = f"{seg.source_text} (VI)"
            seg.status = "translated"

    with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="fake_access_token"), \
         patch.object(GoogleSheetsService, "get_spreadsheet", new_callable=AsyncMock, return_value=SAMPLE_SHEET), \
         patch.object(GoogleDriveService, "create_translated_copy", new_callable=AsyncMock, return_value=copy_mock_resp), \
         patch.object(GoogleSheetsService, "apply_translations_to_copy", new_callable=AsyncMock, return_value=True), \
         patch.object(GoogleSheetsService, "translate_and_update_sheet_titles", new_callable=AsyncMock) as mock_translate_sheets, \
         patch.object(google_job_manager, "_translate_batch", side_effect=fake_translate_batch):

        # Test job_enabled
        await google_job_manager._run_job_pipeline(job_enabled.id)
        assert mock_translate_sheets.call_count == 1

        mock_translate_sheets.reset_mock()

        # Test job_disabled
        await google_job_manager._run_job_pipeline(job_disabled.id)
        assert mock_translate_sheets.call_count == 0


@pytest.mark.asyncio
async def test_google_docs_restores_protected_tokens_in_source_text():
    """Test that protected tokens are restored in source_text before search-and-replace in Google Docs."""
    await init_db()
    async with async_session_maker() as db:
        acc = IntegrationAccount(
            provider="google",
            account_name="Token Test Account",
            email="tokens@example.com",
            encrypted_access_token="mock_token",
            is_active=True,
            is_mock=False
        )
        db.add(acc)
        doc_file = DocumentFile(
            filename="Test_Tokens_Doc",
            file_type="gdoc",
            file_size=1024,
            original_path="doc-tokens-123",
            detected_language="vi"
        )
        db.add(doc_file)
        await db.commit()
        await db.refresh(doc_file)

        job = DocumentJob(
            document_id=doc_file.id,
            status="queued",
            source_language="vi",
            target_language="ja",
            provider="groq",
            model="qwen/qwen3.6-27b",
            style="Technical",
            options_json='{"file_id": "doc-tokens-123", "file_type": "gdoc", "title": "Test_Tokens_Doc", "target_mode": "create"}'
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        seg = DocumentSegment(
            job_id=job.id,
            segment_index=0,
            location_json='{"tab_id": "t.0", "paragraph_index": 0}',
            source_text="Khóa mã hóa __PROTECTED_TICKET_ID_1__ GCM an toàn.",
            protected_tokens_json='{"__PROTECTED_TICKET_ID_1__": "AES-256"}',
            translated_text="AES-256 GCMで暗号化し、安全です。",
            status="translated"
        )
        db.add(seg)
        await db.commit()
        job_id = job.id

    copy_mock_resp = {"id": "copy-doc-tokens-456", "name": "Test_Tokens_Doc_JA"}

    with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="fake_token"), \
         patch.object(GoogleDocsService, "get_document_content", new_callable=AsyncMock, return_value=SAMPLE_DOC), \
         patch.object(GoogleDriveService, "create_translated_copy", new_callable=AsyncMock, return_value=copy_mock_resp), \
         patch.object(GoogleDocsService, "apply_translations_to_copy", new_callable=AsyncMock) as mock_apply, \
         patch.object(GoogleDocsService, "translate_and_update_tab_titles", new_callable=AsyncMock):

        await google_job_manager._run_job_pipeline(job_id)

        assert mock_apply.called
        translations_passed = mock_apply.call_args[1]["translations"]
        assert len(translations_passed) >= 1
        matched_item = next(t for t in translations_passed if "AES-256" in t["source_text"])
        assert "__PROTECTED_TICKET_ID_1__" not in matched_item["source_text"]
        assert "Khóa mã hóa AES-256 GCM an toàn." == matched_item["source_text"]


@pytest.mark.asyncio
async def test_google_translation_sheet_with_images_hybrid():
    async with async_session_maker() as db:
        acc = IntegrationAccount(
            provider="google",
            account_name="Test Workspace Sheets",
            email="test_sheet@google.com",
            encrypted_access_token="mock_token",
            is_active=True,
            is_mock=True
        )
        db.add(acc)

        doc_file = DocumentFile(
            filename="Bảng tính kèm hình ảnh",
            file_type="gsheet",
            file_size=1024,
            original_path="gsheet-img-101",
            detected_language="ja"
        )
        db.add(doc_file)
        await db.commit()
        await db.refresh(doc_file)

        job = DocumentJob(
            document_id=doc_file.id,
            status="queued",
            source_language="ja",
            target_language="vi",
            provider="gemini",
            model="gemini-3.7-flash",
            style="Technical",
            options_json=json.dumps({
                "file_id": "gsheet-img-101",
                "file_type": "gsheet",
                "title": "Bảng tính kèm hình ảnh",
                "translate_images": True,
                "ocr_mode": "paddleocr",
                "convert_to_google_format": True
            })
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    async def fake_translate_batch(*args, **kwargs):
        batch = kwargs.get("batch") or []
        for seg in batch:
            seg.translated_text = f"{seg.source_text} (VI)"
            seg.status = "translated"

    with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="mock_token"), \
         patch.object(google_job_manager, "_translate_batch", side_effect=fake_translate_batch):

        await google_job_manager._run_job_pipeline(job_id)

    async with async_session_maker() as db:
        updated_job = (await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))).scalar_one()
        assert updated_job.status in ("completed", "partially_completed")
        assert "drive.google.com" in (updated_job.output_path or "")
        assert updated_job.total_segments > 0


@pytest.mark.asyncio
async def test_google_translation_sheet_with_images_hybrid_inplace_update():
    """Verifies that in 'update' target_mode with images enabled, Google Sheets calls update_file_content to update target_file_id in-place."""
    async with async_session_maker() as db:
        acc = IntegrationAccount(
            provider="google",
            account_name="Test Workspace Sheets Inplace",
            email="test_sheet_inplace@google.com",
            encrypted_access_token="mock_token",
            is_active=True,
            is_mock=True
        )
        db.add(acc)

        doc_file = DocumentFile(
            filename="Bảng tính cập nhật ảnh",
            file_type="gsheet",
            file_size=1024,
            original_path="gsheet-src-orig-101",
            detected_language="ja"
        )
        db.add(doc_file)
        await db.commit()
        await db.refresh(doc_file)

        target_fid = "existing-translated-sheet-copy-888"
        job = DocumentJob(
            document_id=doc_file.id,
            status="queued",
            source_language="ja",
            target_language="vi",
            provider="gemini",
            model="gemini-3.7-flash",
            style="Technical",
            options_json=json.dumps({
                "file_id": "gsheet-src-orig-101",
                "file_type": "gsheet",
                "title": "Bảng tính cập nhật ảnh",
                "translate_images": True,
                "ocr_mode": "paddleocr",
                "target_mode": "update",
                "target_file_id": target_fid
            })
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    async def fake_translate_batch(*args, **kwargs):
        batch = kwargs.get("batch") or []
        for seg in batch:
            seg.translated_text = f"{seg.source_text} (VI)"
            seg.status = "translated"

    with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="mock_token"), \
         patch.object(google_job_manager, "_translate_batch", side_effect=fake_translate_batch), \
         patch.object(GoogleDriveService, "update_file_content", new_callable=AsyncMock, return_value={"id": target_fid, "status": "updated"}) as mock_update_content, \
         patch.object(GoogleDriveService, "upload_file", new_callable=AsyncMock) as mock_upload_file:

        await google_job_manager._run_job_pipeline(job_id)

        # Must call update_file_content on the existing copy!
        assert mock_update_content.call_count == 1
        call_kwargs = mock_update_content.call_args[1]
        assert call_kwargs["file_id"] == target_fid
        # Must NOT create a brand new file
        assert mock_upload_file.call_count == 0

    async with async_session_maker() as db:
        updated_job = (await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))).scalar_one()
        assert updated_job.status in ("completed", "partially_completed")
        assert target_fid in (updated_job.output_path or "")






