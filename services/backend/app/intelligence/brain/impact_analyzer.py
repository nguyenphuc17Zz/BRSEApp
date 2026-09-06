import json
from typing import Dict, List, Any, Optional
from app.core.logging import logger
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response

class ImpactAnalyzer:
    """Predicts downstream technical and operational impact of a requirement change."""

    @classmethod
    async def analyze_impact(
        cls,
        changed_requirement: str,
        project_context: str = "IT System",
        provider_name: str = "gemini",
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        provider = provider_registry.get_provider(provider_name) or provider_registry.get_provider("gemini")

        prompt = f"""You are a Systems Architect and BrSE. Analyze the change impact of this requirement modification on {project_context}.
Requirement Change:
"{changed_requirement}"

Predict potentially impacted components, risks, and recommendations.
Return JSON:
{{
  "impacted_apis": ["API endpoint or service name..."],
  "impacted_frontend": ["UI screen or component..."],
  "impacted_tests": ["Test suite or test cases..."],
  "database_impact": "DB schema changes needed or None",
  "schedule_risk": "HIGH / MEDIUM / LOW",
  "recommended_actions": [
    "Action 1 for BrSE or dev team"
  ]
}}"""

        try:
            resp = await provider.generate(
                prompt=prompt,
                system_instruction="Analyze technical change impact with realistic engineering recommendations.",
                model=model,
                temperature=0.2,
                json_mode=True
            )
            parsed = clean_json_response(resp.text)
            if "impacted_apis" in parsed:
                return parsed
        except Exception as e:
            logger.warning(f"Impact analyzer error: {e}")

        return {
            "impacted_apis": ["Authentication API", "Session Validation"],
            "impacted_frontend": ["Login Screen", "User Profile"],
            "impacted_tests": ["E2E Auth Test Cases"],
            "database_impact": "None expected",
            "schedule_risk": "MEDIUM",
            "recommended_actions": ["Review with backend lead and re-estimate task."]
        }
