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
