import os
from pathlib import Path

# 1. Force dedicated TEST database path BEFORE any other app imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TEST_DATA_DIR = PROJECT_ROOT / "data"
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
TEST_DB_PATH = TEST_DATA_DIR / "test_comtor_copilot.db"

TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["ENVIRONMENT"] = "test"

# 2. Re-bind database engine & sessionmaker in app.core.database to ensure 100% isolation
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings
settings.DATABASE_URL = TEST_DB_URL

import app.core.database as app_db
app_db.engine = create_async_engine(
    TEST_DB_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False}
)
app_db.async_session_maker = async_sessionmaker(
    app_db.engine,
    class_=AsyncSession,
    expire_on_commit=False
)

import pytest

@pytest.fixture(scope="session", autouse=True)
def verify_test_db_isolation():
    """Asserts that tests are running exclusively against the test database."""
    assert "test_comtor_copilot" in str(app_db.engine.url), "Safety check failed: tests must NEVER connect to production database!"
    yield

@pytest.fixture(autouse=True)
async def auto_init_test_db():
    """Automatically ensures test database schema is created before every test."""
    await app_db.init_db()
    yield
