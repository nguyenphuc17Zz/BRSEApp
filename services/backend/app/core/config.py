import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = BASE_DIR.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DATABASE_URL: str = f"sqlite+aiosqlite:///{DATA_DIR.as_posix()}/comtor_copilot.db"
    SECRET_KEY: str = "antigravity_comtor_copilot_secret_salt_2026"
    
    # AI Providers
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_DEFAULT_MODEL: str = "gemma4:12b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text:latest"
    
    # Defaults
    DEFAULT_PROVIDER: str = "groq"
    DEFAULT_GEMINI_MODEL: str = "gemini-3.7-flash"
    DEFAULT_GROQ_MODEL: str = "openai/gpt-oss-120b"
    
    # Logging
    LOG_LEVEL: str = "INFO"

    # Google OAuth 2.0
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_PROJECT_ID: str = ""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
