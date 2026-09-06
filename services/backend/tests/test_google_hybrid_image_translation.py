import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import async_session_maker, init_db
from app.documents.models import DocumentJob, DocumentSegment, DocumentFile
from app.integrations.models import IntegrationAccount
from app.integrations.google.client import GoogleWorkspaceClient
from app.integrations.google.drive import GoogleDriveService
from app.integrations.google.google_jobs import google_job_manager
from sqlalchemy import select, delete

@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    async with async_session_maker() as db:
        acc = IntegrationAccount(
            provider="google",
            account_name="Google Hybrid Test Acc",
            email="hybrid.test@gmail.com",
            encrypted_access_token="mock_enc_token",
            is_active=True,
            is_mock=True
        )
        db.add(acc)
        await db.commit()
    yield
    async with async_session_maker() as db:
        await db.execute(delete(IntegrationAccount).where(IntegrationAccount.provider == "google"))
        await db.commit()

@pytest.mark.asyncio
async def test_google_drive_export_or_download():
    """Verifies that GoogleDriveService.export_or_download_file correctly handles mock export."""
    target_path = Path("data/temp/test_export.docx")
    try:
        res = await GoogleDriveService.export_or_download_file(
            access_token="mock_token",
            file_id="doc-123",
            file_type="gdoc",
            target_path=target_path,
            is_mock=True
        )
        assert res.exists()
        assert res.read_bytes() == b"Mock exported content"
    finally:
        if target_path.exists():
            target_path.unlink()

@pytest.mark.asyncio
async def test_google_drive_upload_with_target_mime():
    """Verifies that GoogleDriveService.upload_file properly formats target_mime_type."""
    res = await GoogleDriveService.upload_file(
        access_token="mock_token",
        filename="Translated_Doc",
        content_bytes=b"dummy bytes",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        target_mime_type="application/vnd.google-apps.document",
        is_mock=True
    )
    assert res["name"] == "Translated_Doc"
    assert "mock_file" in res["id"]

@pytest.mark.asyncio
async def test_google_hybrid_image_job_pipeline():
    """Verifies end-to-end flow of Hybrid OCR translation job on Google Workspace."""
    async def fake_translate_batch(*args, **kwargs):
        batch = kwargs.get("batch") or []
        for seg in batch:
            seg.translated_text = f"{seg.source_text} (VI Translated)"
            seg.status = "translated"

    with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="valid_mock_token"), \
         patch.object(google_job_manager, "_translate_batch", side_effect=fake_translate_batch):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 1. Start translation with translate_images=True, ocr_mode='paddleocr'
            req_data = {
                "file_id": "gdoc-hybrid-999",
                "file_type": "gdoc",
                "title": "Tài Liệu Kèm Sơ Đồ Kiến Trúc",
                "source_language": "ja",
                "target_language": "vi",
                "translate_images": True,
                "ocr_mode": "paddleocr",
                "convert_to_google_format": True
            }

            res = await ac.post("/api/integrations/google/translate", json=req_data)
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "queued"
            job_id = data["job_id"]

            # Wait briefly for background task to execute
            for _ in range(30):
                await asyncio.sleep(0.1)
                async with async_session_maker() as db:
                    job = (await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))).scalar_one_or_none()
                    if job and job.status in ("completed", "partially_completed", "failed"):
                        break

            async with async_session_maker() as db:
                job = (await db.execute(select(DocumentJob).where(DocumentJob.id == job_id))).scalar_one_or_none()
                assert job is not None
                assert job.status in ("completed", "partially_completed")
                assert "drive.google.com" in (job.output_path or "")
                assert job.progress_percent == 100.0
