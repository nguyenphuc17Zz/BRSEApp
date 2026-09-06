import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.integrations.models import IntegrationAccount, IntegrationCache, SlackChannelMapping
from app.integrations.desktop.agent import desktop_agent

class IntegrationManager:
    """Central registry and lifecycle manager for all workspace and communication integrations."""

    @classmethod
    async def get_health_status(cls, db: AsyncSession) -> Dict[str, Any]:
        """Provides operational diagnostics across Google, Slack, and Desktop Agent."""
        # 1. Google Status
        google_all_res = await db.execute(
            select(IntegrationAccount)
            .where(IntegrationAccount.provider == "google")
            .order_by(IntegrationAccount.is_active.desc(), IntegrationAccount.created_at.desc())
        )
        google_accounts = google_all_res.scalars().all()
        google_active_acc = next((a for a in google_accounts if a.is_active), None) or (google_accounts[0] if google_accounts else None)

        accounts_data = [
            {
                "id": a.id,
                "email": a.email,
                "account_name": a.account_name,
                "is_active": a.id == (google_active_acc.id if google_active_acc else None),
                "is_mock": a.is_mock,
                "last_sync": a.last_sync_at.isoformat() if a.last_sync_at else None,
            }
            for a in google_accounts
        ]

        # 2. Slack Status
        slack_res = await db.execute(select(IntegrationAccount).where(IntegrationAccount.provider == "slack", IntegrationAccount.is_active == True))
        slack_acc = slack_res.scalars().first()

        # 3. Channel mappings
        mappings_cnt = (await db.execute(select(SlackChannelMapping))).scalars().all()

        # 4. Cache count
        cache_cnt = (await db.execute(select(IntegrationCache))).scalars().all()

        desktop_stat = desktop_agent.get_status()

        return {
            "google": {
                "connected": len(google_accounts) > 0,
                "account_name": google_active_acc.account_name if google_active_acc else None,
                "email": google_active_acc.email if google_active_acc else None,
                "is_mock": google_active_acc.is_mock if google_active_acc else False,
                "last_sync": google_active_acc.last_sync_at.isoformat() if google_active_acc and google_active_acc.last_sync_at else None,
                "status": "healthy" if google_accounts else "disconnected",
                "total_accounts": len(google_accounts),
                "accounts": accounts_data
            },
            "slack": {
                "connected": slack_acc is not None,
                "workspace_name": slack_acc.workspace_name if slack_acc else None,
                "is_mock": slack_acc.is_mock if slack_acc else False,
                "mapped_channels": len(mappings_cnt),
                "last_sync": slack_acc.last_sync_at.isoformat() if slack_acc and slack_acc.last_sync_at else None,
                "status": "healthy" if slack_acc else "disconnected"
            },
            "desktop": desktop_stat,
            "cache": {
                "entries_count": len(cache_cnt),
                "retention_policy_days": 7
            }
        }

    @classmethod
    async def clean_cache(cls, db: AsyncSession, all_entries: bool = False) -> int:
        """Cleans expired entries or purges all integration cache."""
        if all_entries:
            stmt = delete(IntegrationCache)
        else:
            now = datetime.datetime.utcnow()
            stmt = delete(IntegrationCache).where(IntegrationCache.expires_at < now)
        res = await db.execute(stmt)
        await db.commit()
        return res.rowcount or 0

integration_manager = IntegrationManager()
