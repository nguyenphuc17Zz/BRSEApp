import json
from typing import Dict, List, Any, Optional
from app.core.logging import logger
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response

class DiffAnalyzer:
    """Compares document versions or old requirements against new conversations to identify changes and conflicts."""

    @classmethod
    async def compare_versions(
        cls,
        text_before: str,
        text_after: str,
        context_label: str = "Requirement Version Comparison",
        provider_name: str = "gemini",
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        provider = provider_registry.get_provider(provider_name) or provider_registry.get_provider("gemini")

        prompt = f"""You are a Lead BrSE performing a "What Changed?" difference analysis between two versions of software specifications/communications.

Original Version / Existing Context:
{text_before}

New Version / New Input:
{text_after}

Identify what was added, removed, modified, and any potential conflicts or breaking changes.
Return JSON:
{{
  "added": [
    {{"item": "...", "description": "..."}}
  ],
  "removed": [
    {{"item": "...", "description": "..."}}
  ],
  "modified": [
    {{"item": "...", "before": "...", "after": "...", "significance": "BREAKING / MINOR"}}
  ],
  "conflicts": [
    {{"issue": "...", "recommendation": "Confirm with client before implementing"}}
  ]
}}"""

        try:
            resp = await provider.generate(
                prompt=prompt,
                system_instruction="Provide precise, high-signal diff analysis for software engineers.",
                model=model,
                temperature=0.1,
                json_mode=True
            )
            parsed = clean_json_response(resp.text)
            if "modified" in parsed or "added" in parsed:
                return parsed
        except Exception as e:
            logger.warning(f"Diff analyzer error: {e}")

        return {
            "added": [{"item": "New input received", "description": text_after[:60]}],
            "removed": [],
            "modified": [],
            "conflicts": []
        }
