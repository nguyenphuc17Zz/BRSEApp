import json
import re
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import logger
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response
from app.intelligence.models import WorkItem, WorkItemEvidence

DECISION_SIGNALS = [r"決定", r"方針", r"これで進めます", r"問題ありません", r"この仕様で", r"了解しました", r"合意", r"approved", r"agreed"]

class DecisionExtractor:
    """Extracts confirmed project decisions from client or management messages."""

    @classmethod
    async def extract_decision(
        cls,
        db: AsyncSession,
        project_id: str,
        source_text: str,
        source_type: str,
        source_id: str,
        author: Optional[str] = None,
        timestamp: Optional[str] = None,
        provider_name: str = "gemini",
        model: Optional[str] = None
    ) -> Optional[WorkItem]:
        # Fast filter
        if not any(re.search(sig, source_text, re.IGNORECASE) for sig in DECISION_SIGNALS):
            return None

        provider = provider_registry.get_provider(provider_name) or provider_registry.get_provider("gemini")

        prompt = f"""Determine if this Japanese message confirms an official software or project decision.
Message:
"{source_text}"

Return JSON:
{{
  "is_decision": true/false,
  "decision_title": "Clear concise summary of what was decided",
  "rationale": "Why this decision was made if stated",
  "decision_maker": "{author or 'Client'}",
  "confidence": 0.95
}}"""

        try:
            resp = await provider.generate(
                prompt=prompt,
                system_instruction="Identify final project decisions accurately. Do not confuse open proposals with confirmed decisions.",
                model=model,
                temperature=0.1,
                json_mode=True
            )
            parsed = clean_json_response(resp.text)
            if not parsed.get("is_decision"):
                return None

            work_item = WorkItem(
                project_id=project_id,
                item_type="DECISION",
                title=parsed.get("decision_title", "Confirmed Decision"),
                description=parsed.get("rationale") or source_text,
                details_json=json.dumps({
                    "decision_maker": parsed.get("decision_maker", author or "Client"),
                    "rationale": parsed.get("rationale", "")
                }, ensure_ascii=False),
                status="CONFIRMED",
                priority="HIGH",
                confidence=float(parsed.get("confidence", 0.92))
            )
            db.add(work_item)
            await db.flush()

            evidence = WorkItemEvidence(
                work_item_id=work_item.id,
                source_type=source_type,
                source_id=source_id,
                quote_text=source_text,
                author=author,
                timestamp=timestamp,
                confidence=work_item.confidence,
                confirmation_status="CONFIRMED"
            )
            db.add(evidence)
            await db.commit()
            return work_item

        except Exception as e:
            logger.warning(f"Decision extraction AI error, falling back to heuristics: {e}")
            work_item = WorkItem(
                project_id=project_id,
                item_type="DECISION",
                title=f"Decision: {source_text[:60]}",
                description=source_text,
                details_json=json.dumps({
                    "decision_maker": author or "Client",
                    "confidence": 0.88
                }, ensure_ascii=False),
                status="CONFIRMED",
                priority="HIGH",
                confidence=0.88
            )
            db.add(work_item)
            await db.flush()
            evidence = WorkItemEvidence(
                work_item_id=work_item.id,
                source_type=source_type,
                source_id=source_id,
                quote_text=source_text,
                author=author,
                timestamp=timestamp,
                confidence=0.88,
                confirmation_status="CONFIRMED"
            )
            db.add(evidence)
            await db.commit()
            return work_item
