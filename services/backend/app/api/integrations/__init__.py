from fastapi import APIRouter
from app.api.integrations.google_router import router as google_router
from app.api.integrations.slack_router import router as slack_router
from app.api.integrations.desktop_router import router as desktop_router
from app.api.integrations.health_router import router as health_router

router = APIRouter(prefix="/api/integrations")
router.include_router(google_router)
router.include_router(slack_router)
router.include_router(desktop_router)
router.include_router(health_router)
