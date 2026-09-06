from fastapi import APIRouter
from app.api.intelligence.work_items_router import router as work_items_router
from app.api.intelligence.intelligence_router import router as intelligence_core_router
from app.api.intelligence.brse_dashboard_router import router as brse_dashboard_router
from app.api.intelligence.line_router import router as line_router
from app.api.intelligence.slack_router import router as slack_router
from app.api.intelligence.automation_router import router as automation_router
from app.api.intelligence.stakeholders_router import router as stakeholders_router

router = APIRouter()
router.include_router(work_items_router)
router.include_router(intelligence_core_router)
router.include_router(brse_dashboard_router)
router.include_router(line_router)
router.include_router(slack_router)
router.include_router(automation_router)
router.include_router(stakeholders_router)
