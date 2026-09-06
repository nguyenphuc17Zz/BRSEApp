from typing import Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.logging import logger
from app.core.security import decrypt_credential
from app.db.models import ProviderConfig
from app.providers.base import AIProvider
from app.providers.gemini import GeminiProvider
from app.providers.groq import GroqProvider
from app.providers.ollama import OllamaProvider

class ProviderRegistry:
    """Manages AI provider instances, credentials, health status, and fallback order."""

    def __init__(self):
        self._providers: Dict[str, AIProvider] = {}
        self._initialized = False

    async def initialize(self, db: Optional[AsyncSession] = None):
        """Initializes providers from database settings, falling back to environment configuration."""
        gemini_key = settings.GEMINI_API_KEY
        groq_key = settings.GROQ_API_KEY
        ollama_url = settings.OLLAMA_BASE_URL
        ollama_model = settings.OLLAMA_DEFAULT_MODEL

        if db:
            result = await db.execute(select(ProviderConfig))
            configs = result.scalars().all()
            for conf in configs:
                if conf.name == "gemini" and conf.api_key_encrypted:
                    gemini_key = decrypt_credential(conf.api_key_encrypted) or gemini_key
                elif conf.name == "groq" and conf.api_key_encrypted:
                    groq_key = decrypt_credential(conf.api_key_encrypted) or groq_key
                elif conf.name == "ollama":
                    ollama_url = conf.base_url or ollama_url
                    ollama_model = conf.default_model or ollama_model

        self._providers["gemini"] = GeminiProvider(api_key=gemini_key, default_model=settings.DEFAULT_GEMINI_MODEL)
        self._providers["groq"] = GroqProvider(api_key=groq_key, default_model=settings.DEFAULT_GROQ_MODEL)
        self._providers["ollama"] = OllamaProvider(base_url=ollama_url, default_model=ollama_model, embed_model=settings.OLLAMA_EMBED_MODEL)
        self._initialized = True
        logger.info("ProviderRegistry successfully initialized adapters: Gemini, Groq, Ollama.")

    def get_provider(self, name: str) -> Optional[AIProvider]:
        if not self._initialized:
            self.sync_init_from_env()
        return self._providers.get(name.lower())

    def sync_init_from_env(self):
        self._providers["gemini"] = GeminiProvider(api_key=settings.GEMINI_API_KEY, default_model=settings.DEFAULT_GEMINI_MODEL)
        self._providers["groq"] = GroqProvider(api_key=settings.GROQ_API_KEY, default_model=settings.DEFAULT_GROQ_MODEL)
        self._providers["ollama"] = OllamaProvider(
            base_url=settings.OLLAMA_BASE_URL,
            default_model=settings.OLLAMA_DEFAULT_MODEL,
            embed_model=settings.OLLAMA_EMBED_MODEL
        )
        self._initialized = True

    def get_all_providers(self) -> Dict[str, AIProvider]:
        if not self._initialized:
            self.sync_init_from_env()
        return self._providers

provider_registry = ProviderRegistry()
