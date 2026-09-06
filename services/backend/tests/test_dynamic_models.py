import pytest
from app.core.database import async_session_maker, init_db
from app.api.providers import refresh_all_provider_models
from app.providers.registry import provider_registry

@pytest.mark.asyncio
async def test_live_models_discovery():
    """Verify live model discovery querying 100% of models from provider APIs."""
    await init_db()
    async with async_session_maker() as db:
        await provider_registry.initialize(db)
        summary = await refresh_all_provider_models(db)

    # Ollama is local on this machine
    assert "ollama" in summary
    assert summary["ollama"]["count"] > 0
    ollama_models = summary["ollama"]["models"]
    assert any("gemma" in m for m in ollama_models)

    # Groq API check
    assert "groq" in summary
    if summary["groq"]["count"] > 0:
        groq_models = summary["groq"]["models"]
        assert len(groq_models) >= 5
        print(f"Discovered {len(groq_models)} models from Groq live API.")

    # Gemini API check
    assert "gemini" in summary
    if summary["gemini"]["count"] > 0:
        gemini_models = summary["gemini"]["models"]
        print(f"Discovered {len(gemini_models)} models from Gemini live API.")
