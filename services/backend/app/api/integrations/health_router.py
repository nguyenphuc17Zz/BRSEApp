from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.integrations.manager import integration_manager

router = APIRouter(prefix="", tags=["Integration Health"])

@router.get("/health")
async def get_integration_health(db: AsyncSession = Depends(get_db)):
    """Provides complete diagnostics and connection state across all integrations."""
    return await integration_manager.get_health_status(db)

@router.post("/cache/clean")
async def clean_integration_cache(all_entries: bool = False, db: AsyncSession = Depends(get_db)):
    """Cleans expired entries (7-day retention) or all cache."""
    cleaned = await integration_manager.clean_cache(db, all_entries=all_entries)
    return {"message": f"Cleaned {cleaned} cache entries.", "entries_removed": cleaned}
