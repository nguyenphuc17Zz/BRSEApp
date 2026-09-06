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

    async def mock_list_files(access_token, folder_id=None, query=None, is_mock=False, shared_drive_id=None, view_mode="my_drive"):
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


