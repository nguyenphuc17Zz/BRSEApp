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
    from app.intelligence import models as intelligence_models  # Ensure intelligence models are registered
    from app.qa import models as qa_models  # Ensure QA Workspace models are registered
    from app.qa import execution_models as qa_exec_models  # Ensure QA Phase 2 execution models are registered
    from app.qa import api_models as qa_api_models  # Ensure QA Phase 3 API testing models are registered
    from app.qa import ui_models as qa_ui_models  # Ensure QA Phase 4 UI automation models are registered
    from app.qa import regression_models as qa_reg_models  # Ensure QA Phase 5 regression models are registered
    from app.qa import data_models as qa_data_models  # Ensure QA Phase 6 data models are registered
    async with engine.begin() as conn:
        # SQLite performance & integrity pragmas
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        await conn.exec_driver_sql("PRAGMA foreign_keys=ON;")
        await conn.run_sync(Base.metadata.create_all)

        # Lightweight additive migration: req_code display code for WorkItem (QA Workspace)
        try:
            cols = (await conn.exec_driver_sql("PRAGMA table_info(work_items);")).fetchall()
            col_names = {c[1] for c in cols} if cols else set()
            if col_names and "req_code" not in col_names:
                await conn.exec_driver_sql("ALTER TABLE work_items ADD COLUMN req_code VARCHAR(20);")
        except Exception as e:
            logger.warning(f"req_code migration notice: {e}")

        # Lightweight additive migration: Phase 2 execution columns for requirement_coverage
        try:
            cov_cols = (await conn.exec_driver_sql("PRAGMA table_info(requirement_coverage);")).fetchall()
            cov_names = {c[1] for c in cov_cols} if cov_cols else set()
            for col_name, col_type in [
                ("exec_total", "INTEGER"), ("exec_executed", "INTEGER"),
                ("exec_passed", "INTEGER"), ("exec_failed", "INTEGER"),
                ("exec_blocked", "INTEGER"), ("exec_status", "VARCHAR(20)"),
                ("last_result", "VARCHAR(20)"), ("last_build", "VARCHAR(100)"),
            ]:
                if cov_names and col_name not in cov_names:
                    await conn.exec_driver_sql(f"ALTER TABLE requirement_coverage ADD COLUMN {col_name} {col_type};")
        except Exception as e:
            logger.warning(f"coverage exec migration notice: {e}")

        # Lightweight additive migration: run_type for TestRun (Phase 5 REGRESSION runs)
        try:
            run_cols = (await conn.exec_driver_sql("PRAGMA table_info(qa_test_runs);")).fetchall()
            run_names = {c[1] for c in run_cols} if run_cols else set()
            if run_names and "run_type" not in run_names:
                await conn.exec_driver_sql("ALTER TABLE qa_test_runs ADD COLUMN run_type VARCHAR(20) DEFAULT 'MANUAL';")
        except Exception as e:
            logger.warning(f"run_type migration notice: {e}")

        # Lightweight additive migration: settings_json for DataQaJob (Phase 6)
        try:
            djob_cols = (await conn.exec_driver_sql("PRAGMA table_info(qa_data_jobs);")).fetchall()
            djob_names = {c[1] for c in djob_cols} if djob_cols else set()
            if djob_names and "settings_json" not in djob_names:
                await conn.exec_driver_sql("ALTER TABLE qa_data_jobs ADD COLUMN settings_json TEXT DEFAULT '{}';")
        except Exception as e:
            logger.warning(f"data job settings migration notice: {e}")
        
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
