import datetime
import json
from typing import Dict, Any, Optional, List
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.core.security import encrypt_credential, decrypt_credential
from app.integrations.models import IntegrationAccount

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/presentations"
]

class GoogleWorkspaceClient:
    """Handles Google OAuth 2.0 authentication, token refresh, and REST API execution."""

    @classmethod
    async def fetch_user_profile(cls, access_token: str) -> Dict[str, str]:
        """Fetches the real email and display name via Drive about API and userinfo API."""
        email = None
        display_name = None

        async with httpx.AsyncClient(timeout=10.0) as http:
            # 1. Primary: Drive about API (works with existing drive tokens)
            try:
                about_resp = await http.get(
                    "https://www.googleapis.com/drive/v3/about?fields=user(emailAddress,displayName)",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                if about_resp.status_code == 200:
                    user_obj = about_resp.json().get("user", {})
                    email = user_obj.get("emailAddress")
                    display_name = user_obj.get("displayName")
                    logger.info(f"Retrieved Google profile from Drive about API: {email} ({display_name})")
            except Exception as e:
                logger.warning(f"Could not retrieve profile from Drive about API: {e}")

            # 2. Secondary: OAuth2 userinfo API
            if not email:
                try:
                    u_resp = await http.get(
                        "https://www.googleapis.com/oauth2/v2/userinfo",
                        headers={"Authorization": f"Bearer {access_token}"}
                    )
                    if u_resp.status_code == 200:
                        u_data = u_resp.json()
                        email = u_data.get("email")
                        display_name = u_data.get("name")
                        logger.info(f"Retrieved Google profile from Userinfo API: {email}")
                except Exception as e:
                    logger.warning(f"Could not retrieve profile from Userinfo API: {e}")

        return {
            "email": email or "connected.google@gmail.com",
            "name": display_name or "Google Workspace"
        }

    @classmethod
    def get_auth_url(cls, client_id: str, redirect_uri: str, state: str = "google_auth") -> str:
        """Generates Google OAuth 2.0 authorization URL."""
        scope_str = " ".join(SCOPES)
        return (
            f"{GOOGLE_AUTH_URL}?"
            f"client_id={client_id}&"
            f"redirect_uri={redirect_uri}&"
            f"response_type=code&"
            f"scope={scope_str}&"
            f"access_type=offline&"
            f"prompt=select_account%20consent&"
            f"state={state}"
        )

    @classmethod
    async def exchange_code_for_tokens(
        cls,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str
    ) -> Dict[str, Any]:
        """Exchanges authorization code for access & refresh tokens."""
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code"
                }
            )
            if resp.status_code != 200:
                logger.error(f"Google OAuth token exchange failed: {resp.text}")
                raise ValueError(f"Failed to exchange Google OAuth code: {resp.text}")
            return resp.json()

    @classmethod
    async def get_valid_access_token(
        cls,
        db: AsyncSession,
        account_id: str,
        client_id: str = "",
        client_secret: str = "",
        force_refresh: bool = False
    ) -> str:
        """Retrieves and automatically refreshes access token if expired or force_refresh is requested."""
        account = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.id == account_id))).scalar_one_or_none()
        if not account:
            raise ValueError("Google integration account not found.")

        # In mock accounts, return decrypted token directly
        if account.is_mock:
            return decrypt_credential(account.encrypted_access_token)

        token = decrypt_credential(account.encrypted_access_token)
        now = datetime.datetime.utcnow()

        # Token still valid and not forcing refresh
        if not force_refresh and account.token_expiry and account.token_expiry > now + datetime.timedelta(minutes=5):
            return token

        # If no refresh token available, return existing token (best effort)
        if not account.encrypted_refresh_token:
            return token

        refresh_token = decrypt_credential(account.encrypted_refresh_token)
        cid = (client_id or settings.GOOGLE_CLIENT_ID or "").strip()
        csec = (client_secret or settings.GOOGLE_CLIENT_SECRET or "").strip()
        if not cid or not csec:
            logger.warning(f"Cannot refresh Google access token for {account.email or account_id}: missing client_id/secret.")
            return token

        try:
            async with httpx.AsyncClient(timeout=15.0) as http:
                resp = await http.post(
                    GOOGLE_TOKEN_URL,
                    data={
                        "client_id": cid,
                        "client_secret": csec,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token"
                    }
                )
                if resp.status_code == 200:
                    data = resp.json()
                    new_token = data.get("access_token")
                    if new_token:
                        account.encrypted_access_token = encrypt_credential(new_token)
                        expires_in = data.get("expires_in", 3600)
                        account.token_expiry = now + datetime.timedelta(seconds=expires_in)
                        account.last_sync_at = now
                        account.last_error = None
                        await db.commit()
                        logger.info(f"Successfully auto-refreshed Google OAuth token for {account.email or account_id}")
                        return new_token
                else:
                    err_msg = f"Failed to refresh Google token: {resp.text}"
                    logger.warning(err_msg)
                    account.last_error = err_msg
                    await db.commit()
        except Exception as e:
            logger.error(f"Error during Google OAuth token refresh: {e}")

        return token
