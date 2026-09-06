from unittest.mock import patch
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.config import settings

import importlib

@pytest.mark.asyncio
async def test_google_credentials_flow():
    orig_client_id = settings.GOOGLE_CLIENT_ID
    orig_client_secret = settings.GOOGLE_CLIENT_SECRET
    orig_project_id = settings.GOOGLE_PROJECT_ID

    gr_mod = importlib.import_module("app.api.integrations.google_router")

    try:
        with patch.object(gr_mod, "update_env_file"):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                # 1. Check initial config endpoint
                res = await ac.get("/api/integrations/google/config")
                assert res.status_code == 200
                data = res.json()
                assert "is_configured" in data
                assert "redirect_uri" in data

                # 2. Upload valid Google OAuth web client credentials payload
                mock_credentials_payload = {
                    "web": {
                        "client_id": "1234567890-abcdefghij.apps.googleusercontent.com",
                        "project_id": "comtor-copilot-auto",
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                        "client_secret": "GOCSPX-mocksecret12345",
                        "redirect_uris": ["http://127.0.0.1:8000/api/integrations/google/callback"]
                    }
                }
                upload_res = await ac.post("/api/integrations/google/config/upload-credentials", json=mock_credentials_payload)
                assert upload_res.status_code == 200
                upload_data = upload_res.json()
                assert upload_data["success"] is True
                assert upload_data["project_id"] == "comtor-copilot-auto"
                assert upload_data["redirect_warning"] is None

                # 3. Check config endpoint reflects new credentials
                conf_res = await ac.get("/api/integrations/google/config")
                assert conf_res.status_code == 200
                conf_data = conf_res.json()
                assert conf_data["is_configured"] is True
                assert conf_data["project_id"] == "comtor-copilot-auto"
                assert "apps.googleusercontent.com" in conf_data["client_id_masked"]

                # 4. Check login-url generates proper auth URL
                login_res = await ac.get("/api/integrations/google/login-url")
                assert login_res.status_code == 200
                login_data = login_res.json()
                assert "https://accounts.google.com/o/oauth2/v2/auth" in login_data["auth_url"]
                assert "1234567890-abcdefghij.apps.googleusercontent.com" in login_data["auth_url"]
    finally:
        settings.GOOGLE_CLIENT_ID = orig_client_id
        settings.GOOGLE_CLIENT_SECRET = orig_client_secret
        settings.GOOGLE_PROJECT_ID = orig_project_id


@pytest.mark.asyncio
async def test_auto_refresh_token_without_explicit_credentials():
    """Verify GoogleWorkspaceClient automatically refreshes expired token using settings without explicit params."""
    import datetime
    from unittest.mock import AsyncMock
    from app.core.database import async_session_maker
    from app.core.security import encrypt_credential, decrypt_credential
    from app.integrations.models import IntegrationAccount
    from app.integrations.google.client import GoogleWorkspaceClient

    settings.GOOGLE_CLIENT_ID = "mock_client_id_123"
    settings.GOOGLE_CLIENT_SECRET = "mock_client_secret_456"

    async with async_session_maker() as db:
        acc = IntegrationAccount(
            provider="google",
            account_name="Test Auto Refresh",
            email="autorefresh@example.com",
            encrypted_access_token=encrypt_credential("old_expired_token"),
            encrypted_refresh_token=encrypt_credential("mock_valid_refresh_token"),
            token_expiry=datetime.datetime.utcnow() - datetime.timedelta(hours=2),
            is_active=True,
            is_mock=False
        )
        db.add(acc)
        await db.commit()
        await db.refresh(acc)

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json = lambda: {
            "access_token": "brand_new_refreshed_token_xyz",
            "expires_in": 3600
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp) as mock_post:
            # Calling WITHOUT client_id or client_secret
            token = await GoogleWorkspaceClient.get_valid_access_token(db, acc.id)
            assert token == "brand_new_refreshed_token_xyz"

            # Check that httpx called token endpoint with settings credentials
            mock_post.assert_called_once()
            called_data = mock_post.call_args[1]["data"]
            assert called_data["client_id"] == "mock_client_id_123"
            assert called_data["client_secret"] == "mock_client_secret_456"
            assert called_data["refresh_token"] == "mock_valid_refresh_token"

            # Check DB updated
            await db.refresh(acc)
            assert decrypt_credential(acc.encrypted_access_token) == "brand_new_refreshed_token_xyz"
            assert acc.token_expiry > datetime.datetime.utcnow()

        await db.delete(acc)
        await db.commit()


@pytest.mark.asyncio
async def test_self_healing_drive_401_retry():
    """Verify GoogleDriveService automatically self-heals when receiving 401 by refreshing token and retrying."""
    from unittest.mock import AsyncMock
    from app.core.database import async_session_maker
    from app.core.security import encrypt_credential
    from app.integrations.models import IntegrationAccount
    from app.integrations.google.drive import GoogleDriveService
    from app.integrations.google.client import GoogleWorkspaceClient

    async with async_session_maker() as db:
        acc = IntegrationAccount(
            provider="google",
            account_name="Test 401 Healing",
            email="healing@example.com",
            encrypted_access_token=encrypt_credential("stale_token"),
            encrypted_refresh_token=encrypt_credential("refresh_token"),
            is_active=True,
            is_mock=False
        )
        db.add(acc)
        await db.commit()
        await db.refresh(acc)

        # 1st call returns 401, 2nd call returns 200 with file list
        resp_401 = AsyncMock()
        resp_401.status_code = 401
        resp_401.text = "Unauthorized"

        resp_200 = AsyncMock()
        resp_200.status_code = 200
        resp_200.json = lambda: {
            "files": [{"id": "f1", "name": "Document.docx", "mimeType": "application/vnd.google-apps.document"}]
        }

        with patch("httpx.AsyncClient.get", side_effect=[resp_401, resp_200]):
            with patch.object(GoogleWorkspaceClient, "get_valid_access_token", new_callable=AsyncMock, return_value="refreshed_token_abc") as mock_get_token:
                files = await GoogleDriveService.list_files(
                    access_token="stale_token",
                    db=db,
                    account_id=acc.id
                )
                assert len(files) == 1
                assert files[0]["name"] == "Document.docx"
                mock_get_token.assert_called_once_with(db, acc.id, force_refresh=True)

        await db.delete(acc)
        await db.commit()
