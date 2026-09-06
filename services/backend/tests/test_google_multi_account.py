import pytest
import datetime
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.main import app
from app.core.database import async_session_maker
from app.core.security import encrypt_credential
from app.integrations.models import IntegrationAccount

@pytest.mark.asyncio
async def test_google_multi_account_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Clean existing google accounts for clean test state
        async with async_session_maker() as db:
            existing = (await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "google"))).scalars().all()
            for acc in existing:
                await db.delete(acc)
            await db.commit()

            # Insert Account 1
            acc1 = IntegrationAccount(
                provider="google",
                account_name="Google Drive (acc1@gmail.com)",
                email="acc1@gmail.com",
                encrypted_access_token=encrypt_credential("token_1"),
                encrypted_refresh_token=encrypt_credential("refresh_1"),
                scopes_json="[]",
                is_active=True,
                is_mock=True,
                token_expiry=datetime.datetime.utcnow() + datetime.timedelta(hours=1),
                last_sync_at=datetime.datetime.utcnow()
            )
            db.add(acc1)
            await db.commit()
            await db.refresh(acc1)
            acc1_id = acc1.id

            # Insert Account 2
            acc2 = IntegrationAccount(
                provider="google",
                account_name="Google Drive (acc2@gmail.com)",
                email="acc2@gmail.com",
                encrypted_access_token=encrypt_credential("token_2"),
                encrypted_refresh_token=encrypt_credential("refresh_2"),
                scopes_json="[]",
                is_active=False,
                is_mock=True,
                token_expiry=datetime.datetime.utcnow() + datetime.timedelta(hours=1),
                last_sync_at=datetime.datetime.utcnow()
            )
            db.add(acc2)
            await db.commit()
            await db.refresh(acc2)
            acc2_id = acc2.id

        # 2. List accounts via API
        resp = await client.get("/api/integrations/google/accounts")
        assert resp.status_code == 200
        accounts = resp.json()
        assert len(accounts) == 2
        emails = [a["email"] for a in accounts]
        assert "acc1@gmail.com" in emails
        assert "acc2@gmail.com" in emails

        # 3. Check health diagnostics reports both accounts
        health_resp = await client.get("/api/integrations/health")
        assert health_resp.status_code == 200
        health_data = health_resp.json()
        assert health_data["google"]["connected"] is True
        assert health_data["google"]["total_accounts"] == 2

        # 4. Activate Account 2
        act_resp = await client.post(f"/api/integrations/google/accounts/{acc2_id}/activate")
        assert act_resp.status_code == 200
        assert act_resp.json()["status"] == "activated"

        # Verify Account 2 is now active in accounts list
        resp = await client.get("/api/integrations/google/accounts")
        accounts = resp.json()
        acc2_item = next(a for a in accounts if a["id"] == acc2_id)
        acc1_item = next(a for a in accounts if a["id"] == acc1_id)
        assert acc2_item["is_active"] is True
        assert acc1_item["is_active"] is False

        # 5. List Drive with specific account_id
        drive_resp = await client.get(f"/api/integrations/google/drive?account_id={acc1_id}")
        assert drive_resp.status_code == 200
        assert drive_resp.json()["account_id"] == acc1_id
        assert drive_resp.json()["account_email"] == "acc1@gmail.com"

        # 6. Disconnect Account 2 (currently active), verify Account 1 is automatically activated
        del_resp = await client.delete(f"/api/integrations/google/accounts/{acc2_id}")
        assert del_resp.status_code == 200

        resp = await client.get("/api/integrations/google/accounts")
        remaining = resp.json()
        assert len(remaining) == 1
        assert remaining[0]["id"] == acc1_id
        assert remaining[0]["is_active"] is True

        # Cleanup remaining test account
        await client.delete(f"/api/integrations/google/accounts/{acc1_id}")
