"""Shared LLM helper for QA engines: user-selected provider with safe fallback chain + heuristic offline mode."""
from typing import Any, Dict, List, Optional

from app.core.logging import logger
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response


def build_chain(preferred: Optional[str]) -> List[str]:
    pref = (preferred or "").strip().lower()
    if pref in ("groq", "gemini", "ollama"):
        rest = [p for p in ("groq", "gemini", "ollama") if p != pref]
        return [pref] + rest
    return ["groq", "gemini", "ollama"]


async def generate_qa_json(
    prompt: str,
    system_instruction: str,
    preferred_provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 1500,
) -> Dict[str, Any]:
    """Calls providers in chain order, returns parsed JSON dict ({} if all fail/offline)."""
    for candidate in build_chain(preferred_provider):
        provider = provider_registry.get_provider(candidate)
        if not provider:
            continue
        try:
            target_model = model if (candidate == (preferred_provider or "").strip().lower() and model) else None
            resp = await provider.generate(
                prompt=prompt,
                system_instruction=system_instruction,
                model=target_model,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=(candidate == "gemini"),
            )
            parsed = clean_json_response(resp.text)
            if isinstance(parsed, dict) and parsed:
                return parsed
        except Exception as e:
            logger.warning(f"QA LLM call failed on '{candidate}': {e}")
            continue
    return {}
