import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import logger
from app.engine.pipeline import translation_pipeline, clean_json_response
from app.engine.prompt import PromptBuilder
from app.providers.registry import provider_registry
from app.schemas.schemas import (
    ExplainRequest, ExplainResponse, ReplyRequest, ReplyResponse,
    RewriteRequest, RewriteResponse, TranslationRequest, TranslationResponse
)

router = APIRouter(prefix="/api", tags=["Translation"])

@router.post("/translate", response_model=TranslationResponse)
async def translate_text(req: TranslationRequest, db: AsyncSession = Depends(get_db)):
    """Translates text with project context, glossary constraints, TM reference, and QA check."""
    try:
        return await translation_pipeline.execute(db=db, request=req)
    except Exception as e:
        logger.error(f"Translation pipeline failure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

from typing import Optional, Dict, Any, List

async def _execute_with_resilient_fallback(
    sys_prompt: str,
    user_prompt: str,
    preferred_provider: Optional[str] = None,
    force_model: Optional[str] = None,
    temperature: float = 0.3
) -> Dict[str, Any]:
    available_providers = list(provider_registry.get_all_providers().keys())
    if not available_providers:
        raise HTTPException(status_code=503, detail="No active AI provider available.")

    chain: List[str] = []
    if preferred_provider and preferred_provider != "auto" and preferred_provider in available_providers:
        chain.append(preferred_provider)

    # Resilient fallback sequence
    for fallback in ["groq", "gemini", "ollama"]:
        if fallback in available_providers and fallback not in chain:
            chain.append(fallback)

    for p in available_providers:
        if p not in chain:
            chain.append(p)

    last_error: Optional[Exception] = None
    for prov_name in chain:
        provider = provider_registry.get_provider(prov_name)
        if not provider:
            continue
        try:
            target_model = force_model if (prov_name == preferred_provider and force_model) else provider.default_model
            logger.info(f"Generating content via provider '{prov_name}' (model: {target_model})...")
            resp_data = await provider.generate(
                prompt=user_prompt,
                system_instruction=sys_prompt,
                model=target_model,
                temperature=temperature,
                json_mode=True,
                timeout=40.0
            )
            parsed = clean_json_response(resp_data.text)
            if parsed:
                return parsed
        except Exception as e:
            logger.warning(f"Provider '{prov_name}' execution failed: {e}. Attempting fallback...")
            last_error = e

    logger.error(f"All providers failed for prompt task. Last error: {last_error}")
    raise HTTPException(status_code=500, detail=f"All AI providers failed. Last error: {str(last_error)}")

@router.post("/explain", response_model=ExplainResponse)
async def explain_translation(req: ExplainRequest):
    """Explains grammar, IT nuances, and terminology in the translation."""
    try:
        sys_prompt, user_prompt = PromptBuilder.build_explain_prompt(
            source_text=req.source_text,
            translation_text=req.translation_text,
            source_lang=req.source_language,
            target_lang=req.target_language
        )
        parsed = await _execute_with_resilient_fallback(
            sys_prompt=sys_prompt,
            user_prompt=user_prompt,
            preferred_provider=req.preferred_provider,
            force_model=req.force_model,
            temperature=0.3
        )
        return ExplainResponse(
            summary=parsed.get("summary", "Summary of translation."),
            grammar_and_nuances=parsed.get("grammar_and_nuances", []),
            technical_terms=parsed.get("technical_terms", []),
            alternative_interpretations=parsed.get("alternative_interpretations", [])
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Explain failed: {e}")
        raise HTTPException(status_code=500, detail=f"Explanation failed: {str(e)}")

@router.post("/reply", response_model=ReplyResponse)
async def generate_reply(req: ReplyRequest):
    """Generates professional reply suggestions across multiple tone styles."""
    try:
        sys_prompt, user_prompt = PromptBuilder.build_reply_prompt(
            source_message=req.source_message,
            history=req.conversation_history,
            reply_lang=req.reply_language,
            user_intent=req.user_intent
        )
        parsed = await _execute_with_resilient_fallback(
            sys_prompt=sys_prompt,
            user_prompt=user_prompt,
            preferred_provider=req.preferred_provider,
            force_model=req.force_model,
            temperature=0.4
        )
        return ReplyResponse(options=parsed.get("options", []))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reply generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Reply generation failed: {str(e)}")

@router.post("/rewrite", response_model=RewriteResponse)
async def rewrite_text(req: RewriteRequest):
    """Rewrites text to adjust tone (e.g. more polite, concise, natural) while preserving semantics."""
    try:
        sys_prompt, user_prompt = PromptBuilder.build_rewrite_prompt(
            text=req.text,
            tone=req.tone,
            lang=req.language
        )
        parsed = await _execute_with_resilient_fallback(
            sys_prompt=sys_prompt,
            user_prompt=user_prompt,
            preferred_provider=req.preferred_provider,
            force_model=req.force_model,
            temperature=0.3
        )
        return RewriteResponse(
            original_text=req.text,
            rewritten_text=parsed.get("rewritten_text", req.text),
            tone=req.tone
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rewrite failed: {e}")
        raise HTTPException(status_code=500, detail=f"Rewrite failed: {str(e)}")
