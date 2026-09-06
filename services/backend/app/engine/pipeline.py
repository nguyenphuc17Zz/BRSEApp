import json
import re
import time
from typing import Dict, List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.models import TranslationSession, TranslationResult
from app.engine.context import context_engine
from app.engine.prompt import PromptBuilder
from app.engine.qa import QAChecker
from app.engine.router import TaskAnalyzer, router_engine
from app.providers.registry import provider_registry
from app.schemas.schemas import (
    CandidateTranslation, TranslationRequest, TranslationResponse,
    UsedGlossaryItem, UsedMemoryItem
)

def detect_language(text: str) -> str:
    """Heuristic detector for Japanese, Vietnamese, and English."""
    if not text or not text.strip():
        return "ja"

    jp_pattern = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]")
    vi_pattern = re.compile(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ]")

    jp_chars = len(jp_pattern.findall(text))
    vi_chars = len(vi_pattern.findall(text))

    if jp_chars > 0 and jp_chars >= vi_chars:
        return "ja"
    if vi_chars > 0:
        return "vi"

    # Latin text without Vietnamese accents is treated as English
    return "en"

def clean_json_response(raw_text: str) -> Dict[str, Any]:
    """Safely extracts JSON from model output, stripping markdown fences and repairing truncation if needed."""
    if not raw_text:
        return {}
    text = raw_text.strip()
    # Strip <think>...</think> tags if model produced reasoning block
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    # Find the outermost {
    start = text.find("{")
    if start == -1:
        return {}

    end = text.rfind("}")
    if end != -1 and end > start:
        candidate = text[start:end+1]
    else:
        candidate = text[start:]

    # First attempt: direct json.loads with strict=False (allows unescaped newlines/tabs in strings)
    try:
        parsed = json.loads(candidate, strict=False)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Second attempt: Smart repair of truncated JSON (e.g. cut off due to max_tokens)
    s = candidate.strip()
    for _ in range(15):
        # Scan character by character to detect unclosed quotes and open delimiters
        in_string = False
        escape = False
        stack = []
        for ch in s:
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch in ('{', '['):
                    stack.append(ch)
                elif ch == '}':
                    if stack and stack[-1] == '{':
                        stack.pop()
                elif ch == ']':
                    if stack and stack[-1] == '[':
                        stack.pop()

        repaired = s
        if in_string:
            if repaired.endswith('\\'):
                repaired = repaired[:-1]
            repaired += '"'

        repaired = re.sub(r",\s*$", "", repaired.strip())
        if repaired.endswith(":"):
            repaired += ' ""'
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)

        for opener in reversed(stack):
            repaired += "]" if opener == "[" else "}"

        try:
            parsed = json.loads(repaired, strict=False)
            if isinstance(parsed, dict) and parsed:
                return parsed
        except Exception:
            # Step back to the last delimiter to drop the broken trailing entry
            last_delim = max(s.rfind(","), s.rfind("{"), s.rfind("["))
            if last_delim > 0:
                s = s[:last_delim].strip()
            else:
                break

    logger.warning(f"Failed to parse or repair JSON. Raw snippet: {raw_text[:120]}...")
    return {}


class TranslationPipeline:
    """End-to-end Translation Orchestrator executing the complete Comtor workflow."""

    async def execute(self, db: AsyncSession, request: TranslationRequest) -> TranslationResponse:
        start_time = time.time()
        source_text = request.source_text.strip()

        # 1. Detect language
        source_lang = request.source_language
        if not source_lang or source_lang == "auto":
            source_lang = detect_language(source_text)

        target_lang = request.target_language
        if target_lang == "auto" or target_lang == source_lang:
            target_lang = "vi" if source_lang == "ja" else "ja"

        # 2. Build intelligent context
        context_package = await context_engine.build_context(
            db=db,
            source_text=source_text,
            project_id=request.project_id,
            style=request.style,
            source_lang=source_lang,
            target_lang=target_lang
        )

        # 3. Task Analysis & Routing
        analysis = TaskAnalyzer.analyze(source_text, project_has_rules=bool(context_package.get("project_instructions")))
        all_providers = provider_registry.get_all_providers()
        available_names = list(all_providers.keys())

        primary_provider_name, fallback_names, model_name = router_engine.select_route(
            analysis=analysis,
            preferred_provider=request.preferred_provider,
            available_providers=available_names
        )

        # If user explicitly requested a specific model, honor it
        if request.force_model and request.force_model.strip():
            model_name = request.force_model.strip()

        # 4. Build modular prompt
        system_instruction, user_prompt = PromptBuilder.build_translation_prompt(
            source_text=source_text,
            source_lang=source_lang,
            target_lang=target_lang,
            context_package=context_package,
            style=request.style
        )

        # 5. Call Provider with automatic fallback
        provider_chain = [primary_provider_name] + fallback_names
        response_data = None
        last_error = None
        used_provider_name = primary_provider_name
        used_model_name = model_name

        for prov_name in provider_chain:
            provider = provider_registry.get_provider(prov_name)
            if not provider:
                continue
            try:
                logger.info(f"Attempting translation via provider '{prov_name}' (model: {provider.default_model})...")
                response_data = await provider.generate(
                    prompt=user_prompt,
                    system_instruction=system_instruction,
                    model=model_name if prov_name == primary_provider_name else provider.default_model,
                    temperature=0.2,
                    json_mode=True,
                    timeout=45.0
                )
                used_provider_name = prov_name
                used_model_name = response_data.model
                break
            except Exception as e:
                logger.warning(f"Provider '{prov_name}' call failed: {e}. Attempting fallback...")
                last_error = e

        if not response_data:
            raise RuntimeError(f"All configured AI providers failed. Last error: {last_error}")

        # 6. Parse and validate JSON structure
        parsed_result = clean_json_response(response_data.text)
        candidates_raw = parsed_result.get("translations", [])

        candidate_translations: List[CandidateTranslation] = []
        for c in candidates_raw:
            if isinstance(c, dict) and "text" in c:
                candidate_translations.append(CandidateTranslation(
                    text=c["text"],
                    style=c.get("style", request.style or "business"),
                    confidence=float(c.get("confidence", 0.9)),
                    reason=c.get("reason")
                ))
            elif isinstance(c, str):
                candidate_translations.append(CandidateTranslation(
                    text=c,
                    style=request.style or "business",
                    confidence=0.9
                ))

        if not candidate_translations:
            candidate_translations.append(CandidateTranslation(
                text=response_data.text,
                style=request.style or "business",
                confidence=0.85
            ))

        primary_translation = candidate_translations[0].text
        ambiguity_detected = bool(parsed_result.get("ambiguity_detected") or len(candidate_translations) > 1)
        ambiguity_reason = parsed_result.get("ambiguity_reason")

        # 7. Run QA verification checks
        qa_warnings = QAChecker.run_qa(
            source_text=source_text,
            translated_text=primary_translation,
            glossary_items=context_package.get("glossary_terms")
        )

        # 8. Record in Translation History Database
        total_latency_ms = int((time.time() - start_time) * 1000)

        # Session handling
        session_id = request.session_id
        if not session_id:
            session = TranslationSession(
                project_id=request.project_id,
                title=source_text[:40] + ("..." if len(source_text) > 40 else "")
            )
            db.add(session)
            await db.flush()
            session_id = session.id

        history_record = TranslationResult(
            session_id=session_id,
            project_id=request.project_id,
            source_text=source_text,
            source_language=source_lang,
            target_language=target_lang,
            style=request.style or "auto",
            provider=used_provider_name,
            model=used_model_name,
            selected_translation=primary_translation,
            candidate_translations_json=json.dumps([c.dict() for c in candidate_translations], ensure_ascii=False),
            ambiguity_detected=ambiguity_detected,
            ambiguity_reason=ambiguity_reason,
            latency_ms=total_latency_ms,
            qa_warnings_json=json.dumps(qa_warnings, ensure_ascii=False),
            used_glossary_json=json.dumps(context_package.get("glossary_terms", []), ensure_ascii=False),
            used_memory_json=json.dumps(context_package.get("translation_memory", []), ensure_ascii=False)
        )
        db.add(history_record)
        await db.commit()
        await db.refresh(history_record)

        # 9. Format response
        used_glossary_items = [
            UsedGlossaryItem(
                source_term=g["source_term"],
                target_term=g["target_term"],
                category=g.get("category")
            ) for g in context_package.get("glossary_terms", [])
        ]

        used_memory_items = [
            UsedMemoryItem(
                source_text=m["source_text"],
                target_text=m["target_text"],
                similarity=m["similarity"]
            ) for m in context_package.get("translation_memory", [])
        ]

        return TranslationResponse(
            result_id=history_record.id,
            session_id=session_id,
            source_language=source_lang,
            target_language=target_lang,
            translations=candidate_translations,
            ambiguity_detected=ambiguity_detected,
            ambiguity_reason=ambiguity_reason,
            provider=used_provider_name,
            model=used_model_name,
            latency_ms=total_latency_ms,
            qa_warnings=qa_warnings,
            used_glossary=used_glossary_items,
            used_memory=used_memory_items,
            detected_terms=parsed_result.get("detected_terms", [])
        )

translation_pipeline = TranslationPipeline()
