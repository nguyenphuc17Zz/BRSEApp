import json
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logging import logger
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response
from app.intelligence.models import WorkItem, WorkItemEvidence

class BugAnalyzer:
    """Detects and structures bug reports from chats or documents."""

    @classmethod
    async def extract_bug(
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
        """Extracts bug details or returns None if text is not a genuine bug."""
        provider = provider_registry.get_provider(provider_name) or provider_registry.get_provider("gemini")

        prompt = f"""Analyze if the following Japanese text reports a genuine software bug or defect.
If it is a feature request, question, or normal discussion, return {{"is_bug": false}}.
If it is a bug, extract structured defect details.

Text:
"{source_text}"

Return JSON:
{{
  "is_bug": true/false,
  "title": "Concise defect title",
  "environment": "Production / Staging / Development / Unknown",
  "steps_to_reproduce": ["Step 1", "Step 2..."],
  "expected_result": "What should have happened",
  "actual_result": "What went wrong / error code",
  "severity": "CRITICAL / HIGH / MEDIUM / LOW",
  "workaround": "Workaround if mentioned or Not available",
  "confidence": 0.92
}}"""

        try:
            resp = await provider.generate(
                prompt=prompt,
                system_instruction="You are a QA Lead and BrSE. Accurately identify defects and extract reproduction details.",
                model=model,
                temperature=0.1,
                json_mode=True
            )
            parsed = clean_json_response(resp.text)
            if not parsed.get("is_bug"):
                return None

            work_item = WorkItem(
                project_id=project_id,
                item_type="BUG",
                title=parsed.get("title", "Reported Defect"),
                description=f"Expected: {parsed.get('expected_result')}\nActual: {parsed.get('actual_result')}",
                details_json=json.dumps({
                    "environment": parsed.get("environment", "Unknown"),
                    "steps": parsed.get("steps_to_reproduce", []),
                    "expected": parsed.get("expected_result"),
                    "actual": parsed.get("actual_result"),
                    "workaround": parsed.get("workaround", "None")
                }, ensure_ascii=False),
                status="PROPOSED",
                priority=parsed.get("severity", "HIGH"),
                confidence=float(parsed.get("confidence", 0.90))
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
                confirmation_status="PROPOSED"
            )
            db.add(evidence)
            await db.commit()
            return work_item

        except Exception as e:
            logger.warning(f"Bug analysis AI error, falling back to heuristics: {e}")
            # Heuristic detection
            bug_keywords = ["エラー", "不具合", "バグ", "動かない", "失敗", "500", "404", "crash", "bug", "error", "fail"]
            if any(k in source_text.lower() for k in bug_keywords):
                work_item = WorkItem(
                    project_id=project_id,
                    item_type="BUG",
                    title=f"Reported Bug: {source_text[:50]}",
                    description=f"Defect identified: {source_text}",
                    details_json=json.dumps({
                        "environment": "Unknown",
                        "steps": [],
                        "expected": "Normal operation",
                        "actual": source_text,
                        "workaround": "None"
                    }, ensure_ascii=False),
                    status="PROPOSED",
                    priority="HIGH",
                    confidence=0.82
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
                    confidence=0.85,
                    confirmation_status="PROPOSED"
                )
                db.add(evidence)
                await db.commit()
                return work_item
            return None
