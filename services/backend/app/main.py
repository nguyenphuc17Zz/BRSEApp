from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dashboard import router as dashboard_router
from app.api.documents import router as documents_router
from app.api.integrations import router as integrations_router
from app.api.glossary import router as glossary_router
from app.api.history import router as history_router
from app.api.memory import router as memory_router
from app.api.projects import router as projects_router
from app.api.providers import router as providers_router
from app.api.translate import router as translate_router
from app.api.intelligence import router as intelligence_router
from app.core.config import settings
from app.core.database import init_db, async_session_maker
from app.core.logging import logger
from app.db.seed import seed_data
from app.providers.registry import provider_registry

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Comtor / BrSE Copilot Backend...")
    await init_db()
    await seed_data()
    async with async_session_maker() as db:
        await provider_registry.initialize(db)
        # Auto-clean mock data and sync meeting decisions/questions on startup
        try:
            from app.intelligence.sync_cleanup_service import cleanup_mock_data_and_sync
            await cleanup_mock_data_and_sync(db)
        except Exception as e:
            logger.warning(f"Initial sync cleanup error: {e}")

        # Auto-fetch live models from all providers on startup as requested
        try:
            from app.api.providers import refresh_all_provider_models
            logger.info("Synchronizing live models from Gemini, Groq, and Ollama APIs...")
            await refresh_all_provider_models(db)
            logger.info("Model catalog synchronized successfully from provider APIs.")
        except Exception as e:
            logger.warning(f"Initial model discovery error: {e}")
    logger.info("Backend initialized and ready for requests.")
    yield
    logger.info("Shutting down backend...")

app = FastAPI(
    title="AI Comtor / BrSE Copilot API",
    description="Enterprise-grade Japanese ↔ Vietnamese Translation & Knowledge Copilot for IT Communicators & BrSE",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware for local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
        "http://localhost:5175", "http://127.0.0.1:5175",
        "http://localhost:3000", "http://127.0.0.1:3000"
    ],
    allow_origin_regex=r"^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register REST Routers
app.include_router(translate_router)
app.include_router(projects_router)
app.include_router(glossary_router)
app.include_router(memory_router)
app.include_router(history_router)
app.include_router(providers_router)
app.include_router(dashboard_router)
app.include_router(documents_router)
app.include_router(integrations_router)
app.include_router(intelligence_router)

@app.get("/api/health")
async def health_check():
    """System health check endpoint."""
    all_provs = provider_registry.get_all_providers()
    return {
        "status": "online",
        "environment": settings.ENVIRONMENT,
        "configured_providers": list(all_provs.keys()),
        "default_provider": settings.DEFAULT_PROVIDER,
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
