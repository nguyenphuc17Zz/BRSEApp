from unittest.mock import patch, AsyncMock
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import async_session_maker, init_db
from app.integrations.models import IntegrationAccount
from app.integrations.google.client import GoogleWorkspaceClient
from app.integrations.google.drive import GoogleDriveService

from sqlalchemy import delete

@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    async with async_session_maker() as db:
        acc = IntegrationAccount(
            provider="google",
            account_name="Test Google Account",
            email="test@gmail.com",
            encrypted_access_token="mock_enc_token",
            is_active=True,
            is_mock=False
        )
        db.add(acc)
        await db.commit()
    yield
    async with async_session_maker() as db:
        await db.execute(delete(IntegrationAccount).where(IntegrationAccount.provider == "google"))
        await db.commit()

@pytest.mark.asyncio
async def test_google_drive_crud_operations():
    mock_files = [
        {"id": "f-1", "name": "Document 1", "type": "doc", "size": 1024, "modified_at": "2026-09-01T00:00:00Z"}
    ]
    mock_folder = {"id": "folder-123", "name": "Kế Hoạch Dịch Q3 2026", "type": "folder", "modified_at": "2026-09-01T00:00:00Z"}
    mock_uploaded = {"id": "file-456", "name": "tailieu_dich_sample.docx", "type": "other", "size": 500, "modified_at": "2026-09-01T00:00:00Z"}
    mock_renamed = {"id": "file-456", "name": "tailieu_dich_sample_RENAMED.docx", "type": "other", "size": 500, "modified_at": "2026-09-01T00:00:00Z"}

    with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="valid_token"), \
         patch.object(GoogleDriveService, "list_files", new_callable=AsyncMock, return_value=mock_files), \
         patch.object(GoogleDriveService, "create_folder", new_callable=AsyncMock, return_value=mock_folder), \
         patch.object(GoogleDriveService, "upload_file", new_callable=AsyncMock, return_value=mock_uploaded), \
         patch.object(GoogleDriveService, "rename_file", new_callable=AsyncMock, return_value=mock_renamed), \
         patch.object(GoogleDriveService, "delete_file", new_callable=AsyncMock, return_value={"status": "deleted"}):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 1. List Drive files
            list_res = await ac.get("/api/integrations/google/drive")
            assert list_res.status_code == 200
            files = list_res.json()["files"]
            assert len(files) > 0

            # 2. Create a new folder
            create_res = await ac.post("/api/integrations/google/drive/folders", json={"name": "Kế Hoạch Dịch Q3 2026"})
            assert create_res.status_code == 200
            new_folder = create_res.json()["folder"]
            assert new_folder["name"] == "Kế Hoạch Dịch Q3 2026"
            assert new_folder["type"] == "folder"

            # 3. Upload a test document into this folder
            file_content = b"Test document content for Google Drive Explorer CRUD"
            files_data = {"file": ("tailieu_dich_sample.docx", file_content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
            upload_res = await ac.post(
                "/api/integrations/google/drive/upload",
                files=files_data,
                data={"parent_folder_id": "folder-123"}
            )
            assert upload_res.status_code == 200
            uploaded_file = upload_res.json()["file"]
            assert uploaded_file["name"] == "tailieu_dich_sample.docx"

            # 4. Rename the uploaded file
            rename_res = await ac.patch(
                "/api/integrations/google/drive/files/file-456",
                json={"new_name": "tailieu_dich_sample_RENAMED.docx"}
            )
            assert rename_res.status_code == 200
            renamed_file = rename_res.json()["file"]
            assert renamed_file["name"] == "tailieu_dich_sample_RENAMED.docx"

            # 5. Delete the file
            delete_res = await ac.delete("/api/integrations/google/drive/files/file-456")
            assert delete_res.status_code == 200
            assert delete_res.json()["status"] == "deleted"

            # 6. Delete the folder
            delete_folder_res = await ac.delete("/api/integrations/google/drive/files/folder-123")
            assert delete_folder_res.status_code == 200
            assert delete_folder_res.json()["status"] == "deleted"

@pytest.mark.asyncio
async def test_google_drive_view_modes():
    recorded_calls = []

    async def mock_list_files(access_token, folder_id=None, query=None, is_mock=False, shared_drive_id=None, view_mode="my_drive", **kwargs):
        recorded_calls.append({"folder_id": folder_id, "query": query, "view_mode": view_mode})
        return [{"id": "item-1", "name": f"File in {view_mode}", "type": "doc"}]

    with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="valid_token"), \
         patch.object(GoogleDriveService, "list_files", side_effect=mock_list_files):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 1. Default view_mode (my_drive)
            res1 = await ac.get("/api/integrations/google/drive")
            assert res1.status_code == 200
            assert recorded_calls[-1]["view_mode"] == "my_drive"

            # 2. shared_with_me
            res2 = await ac.get("/api/integrations/google/drive?view_mode=shared_with_me")
            assert res2.status_code == 200
            assert recorded_calls[-1]["view_mode"] == "shared_with_me"

            # 3. recent
            res3 = await ac.get("/api/integrations/google/drive?view_mode=recent")
            assert res3.status_code == 200
            assert recorded_calls[-1]["view_mode"] == "recent"


@pytest.mark.asyncio
async def test_google_drive_file_type_categorization():
    raw_files = [
        {"id": "1", "name": "Báo cáo.docx", "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        {"id": "2", "name": "Thuyết trình.pptx", "mimeType": "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
        {"id": "3", "name": "Bảng tính.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        {"id": "4", "name": "HuongDan.pdf", "mimeType": "application/pdf"},
        {"id": "5", "name": "Logo.png", "mimeType": "image/png"},
        {"id": "6", "name": "Tài liệu cũ.doc", "mimeType": "application/msword"},
        {"id": "7", "name": "BangGia.xls", "mimeType": "application/vnd.ms-excel"},
        {"id": "8", "name": "SlideCu.ppt", "mimeType": "application/vnd.ms-powerpoint"},
        {"id": "9", "name": "DuLieu.csv", "mimeType": "text/csv"},
        {"id": "10", "name": "TaiLieu.zip", "mimeType": "application/zip"},
        {"id": "11", "name": "ThuMuc", "mimeType": "application/vnd.google-apps.folder"}
    ]

    from unittest.mock import MagicMock
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"files": raw_files}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        res = await GoogleDriveService.list_files(access_token="test_tok")
        by_id = {f["id"]: f["type"] for f in res}
        assert by_id["1"] == "doc"
        assert by_id["2"] == "slide"
        assert by_id["3"] == "sheet"
        assert by_id["4"] == "pdf"
        assert by_id["5"] == "image"
        assert by_id["6"] == "doc"
        assert by_id["7"] == "sheet"
        assert by_id["8"] == "slide"
        assert by_id["9"] == "sheet"
        assert by_id["10"] == "archive"
        assert by_id["11"] == "folder"


@pytest.mark.asyncio
async def test_google_drive_batch_delete():
    deleted_ids = []

    async def mock_delete_file(access_token, file_id, is_mock=False):
        deleted_ids.append(file_id)
        return {"status": "deleted", "id": file_id}

    with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="valid_token"), \
         patch.object(GoogleDriveService, "delete_file", side_effect=mock_delete_file):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Test batch delete with 3 files
            res = await ac.post(
                "/api/integrations/google/drive/files/batch-delete",
                json={"file_ids": ["fid-1", "fid-2", "fid-3"]}
            )
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "success"
            assert data["deleted_count"] == 3
            assert data["failed_count"] == 0
            assert set(deleted_ids) == {"fid-1", "fid-2", "fid-3"}

            # Test empty list
            res_empty = await ac.post(
                "/api/integrations/google/drive/files/batch-delete",
                json={"file_ids": []}
            )
            assert res_empty.status_code == 200
            assert res_empty.json()["deleted_count"] == 0

@pytest.mark.asyncio
async def test_google_drive_download_single():
    mock_bytes = b"Mock exported docx binary bytes"
    mock_name = "BaoCao_Q3_2026.docx"
    mock_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="valid_token"), \
         patch.object(GoogleDriveService, "export_or_download_file_bytes", new_callable=AsyncMock, return_value=(mock_bytes, mock_name, mock_mime)):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get("/api/integrations/google/drive/files/doc-123/download")
            assert res.status_code == 200
            assert res.content == mock_bytes
            assert "Content-Disposition" in res.headers
            assert "BaoCao_Q3_2026.docx" in res.headers["Content-Disposition"]
            assert res.headers["Content-Type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml.document")

@pytest.mark.asyncio
async def test_google_drive_batch_download_zip():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("File1.docx", b"Content of file 1")
        zf.writestr("File2.xlsx", b"Content of file 2")
    zip_bytes = buf.getvalue()
    zip_name = "drive_download_20260907_120000.zip"

    with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="valid_token"), \
         patch.object(GoogleDriveService, "download_files_as_zip", new_callable=AsyncMock, return_value=(zip_bytes, zip_name)):

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post(
                "/api/integrations/google/drive/files/batch-download",
                json={"file_ids": ["f-1", "f-2"]}
            )
            assert res.status_code == 200
            assert res.headers["Content-Type"] == "application/zip"
            assert "Content-Disposition" in res.headers
            assert "drive_download_20260907_120000.zip" in res.headers["Content-Disposition"]

            # Verify it's a valid ZIP
            zf_check = zipfile.ZipFile(io.BytesIO(res.content))
            namelist = zf_check.namelist()
            assert "File1.docx" in namelist
            assert "File2.xlsx" in namelist




