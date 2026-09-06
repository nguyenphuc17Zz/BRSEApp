import json
import re
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response
from app.intelligence.models import WorkItem, WorkItemEvidence

class RequirementExtractor:
    """Extracts normalized requirements, tracks version changes, and detects project conflicts."""

    @classmethod
    async def extract_and_validate(
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
    ) -> List[Dict[str, Any]]:
        """Extracts requirements, checks for conflicts with existing requirements, and returns proposals."""
        provider = provider_registry.get_provider(provider_name) or provider_registry.get_provider("gemini")

        # Load existing confirmed requirements for this project
        existing_res = await db.execute(
            select(WorkItem).where(
                WorkItem.project_id == project_id,
                WorkItem.item_type == "REQUIREMENT",
                WorkItem.status.in_(["CONFIRMED", "IN_PROGRESS", "PROPOSED"])
            )
        )
        existing_items = existing_res.scalars().all()
        existing_context = [
            f"- REQ-{item.id[:6]}: {item.title} (Details: {item.details_json})"
            for item in existing_items
        ]

        prompt = f"""You are a senior BrSE analyzing technical text for software requirements.
Extract explicit or strongly implied requirements from the text below.
Compare each requirement against the list of EXISTING requirements for conflict or contradictions.

Source Text:
"{source_text}"

Existing Project Requirements:
{chr(10).join(existing_context) if existing_context else "(No existing requirements registered yet)"}

Return JSON with format:
{{
  "requirements": [
    {{
      "title": "Brief requirement title",
      "actor": "User / System / Admin / etc.",
      "action": "What must be done",
      "condition": "Precondition or trigger",
      "expected_behavior": "What the system will output or do",
      "priority": "CRITICAL / HIGH / MEDIUM / LOW",
      "confidence": 0.95,
      "conflict_detected": true/false,
      "conflict_description": "Explanation of discrepancy with existing requirement if any",
      "conflicted_with_id": "Existing REQ-xxx ID if conflict exists",
      "evidence_quote": "Exact phrase from source text"
    }}
  ]
}}"""

        extracted_results: List[Dict[str, Any]] = []

        try:
            resp = await provider.generate(
                prompt=prompt,
                system_instruction="You are a strict requirements engineer. Normalize requirements accurately and flag genuine contradictions.",
                model=model,
                temperature=0.1,
                json_mode=True
            )
            parsed = clean_json_response(resp.text)
            extracted_results = parsed.get("requirements", [])
        except Exception as e:
            logger.warning(f"Requirement extraction error: {e}")

        # If offline or simple heuristic fallback
        if not extracted_results and any(k in source_text for k in ["仕様", "要件", "機能", "必須", "実装", "方針", "すること"]):
            extracted_results = [{
                "title": source_text[:60],
                "actor": "User",
                "action": "Implement required feature",
                "condition": "Standard operation",
                "expected_behavior": source_text,
                "priority": "HIGH",
                "confidence": 0.80,
                "conflict_detected": False,
                "conflict_description": None,
                "conflicted_with_id": None,
                "evidence_quote": source_text
            }]

        # Convert to WorkItem candidate objects
        saved_items = []
        for req in extracted_results:
            is_conflict = req.get("conflict_detected", False)
            status = "CONFLICT" if is_conflict else "PROPOSED"

            work_item = WorkItem(
                project_id=project_id,
                item_type="REQUIREMENT",
                title=req.get("title", "Proposed Requirement"),
                description=req.get("expected_behavior") or req.get("action", ""),
                details_json=json.dumps({
                    "actor": req.get("actor", "Unknown"),
                    "action": req.get("action", ""),
                    "condition": req.get("condition", "Not specified"),
                    "priority": req.get("priority", "MEDIUM"),
                }, ensure_ascii=False),
                status=status,
                priority=req.get("priority", "MEDIUM"),
                confidence=float(req.get("confidence", 0.85)),
                is_conflict=is_conflict,
                conflict_notes=req.get("conflict_description")
            )
            db.add(work_item)
            await db.flush()

            # Add Evidence
            evidence = WorkItemEvidence(
                work_item_id=work_item.id,
                source_type=source_type,
                source_id=source_id,
                quote_text=req.get("evidence_quote") or source_text,
                author=author,
                timestamp=timestamp,
                confidence=float(req.get("confidence", 0.90)),
                confirmation_status="PROPOSED"
            )
            db.add(evidence)
            saved_items.append(work_item)

        await db.commit()
        return [
            {
                "id": item.id,
                "title": item.title,
                "description": item.description,
                "status": item.status,
                "is_conflict": item.is_conflict,
                "conflict_notes": item.conflict_notes,
                "confidence": item.confidence
            }
            for item in saved_items
        ]
