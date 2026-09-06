from typing import AsyncGenerator
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings
from app.core.logging import logger

class Base(DeclarativeBase):
    pass

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False}
)

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """Initializes SQLite database, enables WAL mode and foreign keys, and creates tables."""
    from app.db import models  # Ensure all core models are registered
    from app.documents import models as doc_models  # Ensure document translation models are registered
    from app.integrations import models as integration_models  # Ensure integration models are registered
    from app.intelligence import models as intelligence_models  # Ensure Phase 4 intelligence models are registered
    async with engine.begin() as conn:
        # SQLite performance & integrity pragmas
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON;")
        await conn.run_sync(Base.metadata.create_all)
        
        # Setup SQLite FTS5 table for Glossary and Translation Memory fast search
        try:
            await conn.exec_driver_sql("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_glossary USING fts5(
                    term_id UNINDEXED,
                    source_term,
                    target_term,
                    definition,
                    tokenize='unicode61'
                );
            """)
            await conn.exec_driver_sql("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_memory USING fts5(
                    memory_id UNINDEXED,
                    source_text,
                    target_text,
                    tokenize='unicode61'
                );
            """)
            await conn.exec_driver_sql("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_project_documents USING fts5(
                    chunk_id UNINDEXED,
                    project_id,
                    file_id UNINDEXED,
                    filename,
                    chunk_index UNINDEXED,
                    content,
                    tokenize='unicode61'
                );
            """)
        except Exception as e:
            logger.warning(f"FTS5 virtual table initialization notice: {e}")
            
    logger.info("Database initialized successfully.")
