import asyncio
import json
from sqlalchemy import select
from app.core.config import settings
from app.core.database import async_session_maker, init_db
from app.core.logging import logger
from app.core.security import encrypt_credential
from app.db.models import (
    Project, ProjectInstruction, GlossaryTerm, TranslationMemory,
    ProviderConfig, RoutingRule
)

async def seed_data():
    """Initializes and seeds sample IT Comtor demonstration data and provider credentials."""
    await init_db()
    async with async_session_maker() as db:
        # Seed AI Provider Configurations with encrypted keys (Gemini, Groq, Ollama)
        providers_data = [
            {
                "name": "gemini",
                "display_name": "Google Gemini",
                "api_key_encrypted": encrypt_credential(settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None,
                "base_url": "https://generativelanguage.googleapis.com/v1beta",
                "default_model": settings.DEFAULT_GEMINI_MODEL,
                "available_models_json": json.dumps(["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-2.5-flash", "gemini-2.0-flash"]),
                "priority": 1,
                "is_enabled": True
            },
            {
                "name": "groq",
                "display_name": "Groq Cloud",
                "api_key_encrypted": encrypt_credential(settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None,
                "base_url": "https://api.groq.com/openai/v1",
                "default_model": settings.DEFAULT_GROQ_MODEL,
                "available_models_json": json.dumps(["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]),
                "priority": 2,
                "is_enabled": True
            },
            {
                "name": "ollama",
                "display_name": "Ollama (Local AI)",
                "api_key_encrypted": None,
                "base_url": settings.OLLAMA_BASE_URL,
                "default_model": settings.OLLAMA_DEFAULT_MODEL,
                "available_models_json": json.dumps(["gemma4:12b", "aya-expanse:8b", "nomic-embed-text:latest"]),
                "priority": 3,
                "is_enabled": True
            }
        ]

        for p_data in providers_data:
            chk = await db.execute(select(ProviderConfig).where(ProviderConfig.name == p_data["name"]))
            if not chk.scalar_one_or_none():
                db.add(ProviderConfig(**p_data))

        await db.commit()
        logger.info("Demo data and provider settings seeded successfully!")

if __name__ == "__main__":
    asyncio.run(seed_data())
