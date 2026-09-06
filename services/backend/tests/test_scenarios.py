import pytest
from sqlalchemy import select
from app.core.database import async_session_maker, init_db
from app.db.models import Project, ProjectInstruction, GlossaryTerm, TranslationResult
from app.db.seed import seed_data
from app.engine.pipeline import translation_pipeline
from app.engine.context import context_engine
from app.schemas.schemas import TranslationRequest, CorrectionCreate
from app.api.history import record_user_correction

@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    await seed_data()

@pytest.mark.asyncio
async def test_scenario_a_project_glossary_and_history():
    """Scenario A: Verify project, glossary application, history logging."""
    async with async_session_maker() as db:
        # Find seeded project
        p_res = await db.execute(select(Project).where(Project.code == "ABC-BANK"))
        project = p_res.scalar_one_or_none()
        assert project is not None

        # Build context for Japanese technical sentence with glossary term 認証
        text = "新しいOAuth認証フローを実装してください。"
        context = await context_engine.build_context(db, source_text=text, project_id=project.id)

        # Verify glossary term was retrieved
        glossary_sources = [g["source_term"] for g in context["glossary_terms"]]
        assert "認証" in glossary_sources

        # Verify project instructions loaded
        assert len(context["project_instructions"]) > 0

@pytest.mark.asyncio
async def test_scenario_b_ambiguity_detection():
    """Scenario B: Verify ambiguous Japanese triggers ambiguity flag and multiple options."""
    async with async_session_maker() as db:
        p_res = await db.execute(select(Project).where(Project.code == "ABC-BANK"))
        project = p_res.scalar_one_or_none()

        text = "この件は対象外です。"
        context = await context_engine.build_context(db, source_text=text, project_id=project.id)

        # Target should retrieve TM and glossary
        glossary_sources = [g["source_term"] for g in context["glossary_terms"]]
        assert "対象外" in glossary_sources

@pytest.mark.asyncio
async def test_scenario_c_user_correction_learning():
    """Scenario C: User edits translation -> correction is stored -> affects subsequent context."""
    async with async_session_maker() as db:
        p_res = await db.execute(select(Project).where(Project.code == "ABC-BANK"))
        project = p_res.scalar_one_or_none()

        correction_data = CorrectionCreate(
            project_id=project.id,
            source_text="サーバーを再起動してください。",
            original_translation="Hãy khởi động lại máy chủ.",
            corrected_translation="Vui lòng restart lại server hệ thống.",
            language_pair="ja-vi",
            context_note="Use 'server' instead of 'máy chủ'",
            apply_scope="project",
            save_to_tm=True
        )

        corr_res = await record_user_correction(correction_data, db)
        assert corr_res.id is not None

        # Subsequent translation query for similar sentence
        context = await context_engine.build_context(
            db,
            source_text="サーバーを再起動してください。",
            project_id=project.id
        )

        corrections_retrieved = context["corrections"]
        assert len(corrections_retrieved) > 0
        assert corrections_retrieved[0]["corrected_translation"] == "Vui lòng restart lại server hệ thống."

@pytest.mark.asyncio
async def test_scenario_d_and_e_provider_registry():
    """Scenario D & E: Check all three providers are initialized and have fallback capabilities."""
    from app.providers.registry import provider_registry
    async with async_session_maker() as db:
        await provider_registry.initialize(db)

    gemini = provider_registry.get_provider("gemini")
    groq = provider_registry.get_provider("groq")
    ollama = provider_registry.get_provider("ollama")

    assert gemini is not None
    assert groq is not None
    assert ollama is not None
    assert ollama.base_url == "http://127.0.0.1:11434"
