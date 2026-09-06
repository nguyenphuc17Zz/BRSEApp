import json
from typing import Dict, List, Any, Optional
from app.core.logging import logger
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response

class ConversationAnalyzer:
    """Multi-source conversation analyzer for Slack, LINE, and manual chat transcripts."""

    @classmethod
    async def analyze_conversation(
        cls,
        messages: List[Dict[str, Any]],
        project_name: str = "Project Workspace",
        provider_name: str = "gemini",
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Produces structured summary, timeline, requirements, decisions, TODOs, risks, and open questions."""
        provider = provider_registry.get_provider(provider_name) or provider_registry.get_provider("gemini")

        # Format transcript for prompt
        transcript_lines = []
        for m in messages:
            sender = m.get("username") or m.get("sender") or m.get("user", "Unknown")
            text = m.get("text", "")
            ts = m.get("ts") or m.get("timestamp", "")
            transcript_lines.append(f"[{ts}] {sender}: {text}")

        transcript_str = "\n".join(transcript_lines)

        prompt = f"""You are an elite IT BrSE (Bridge Software Engineer) analyzing a technical Japanese conversation for {project_name}.
Extract structured project intelligence with exact evidence. Do not hallucinate facts or commitments.

Conversation Transcript:
{transcript_str}

Analyze and return JSON matching this exact structure:
{{
  "summary": {{
    "context": "Brief 1-2 sentence context of discussion",
    "main_topic": "Topic title",
    "urgency": "HIGH / MEDIUM / LOW"
  }},
  "timeline": [
    {{"timestamp": "...", "speaker": "...", "event": "Brief description of statement"}}
  ],
  "decisions": [
    {{"title": "...", "status": "CONFIRMED / PROPOSED", "evidence": "exact quote from message"}}
  ],
  "requirements": [
    {{"title": "...", "actor": "...", "action": "...", "condition": "...", "confidence": 0.95, "evidence": "exact quote"}}
  ],
  "todos": [
    {{"task": "...", "assignee": "Name or Unassigned", "deadline": "Resolved date or Unspecified", "priority": "HIGH / MEDIUM / LOW", "evidence": "exact quote"}}
  ],
  "risks": [
    {{"risk": "...", "impact": "...", "recommendation": "...", "confidence": 0.85, "evidence": "exact quote"}}
  ],
  "open_questions": [
    {{"question": "...", "needed_from": "Client / Team / BrSE", "evidence": "exact quote"}}
  ]
}}"""

        try:
            resp = await provider.generate(
                prompt=prompt,
                system_instruction="You are a meticulous BrSE analyst. Extract evidence-backed requirements, decisions, and action items in strict JSON.",
                model=model,
                temperature=0.1,
                json_mode=True
            )
            parsed = clean_json_response(resp.text)
            if "summary" in parsed:
                return parsed
        except Exception as e:
            logger.warning(f"AI conversation analysis error: {e}")

        # Reliable fallback analysis if offline
        return {
            "summary": {
                "context": f"Conversation in {project_name} containing {len(messages)} messages.",
                "main_topic": "Project Communication",
                "urgency": "MEDIUM"
            },
            "timeline": [
                {"timestamp": m.get("ts", ""), "speaker": m.get("username") or m.get("sender", "Unknown"), "event": m.get("text", "")[:60]}
                for m in messages
            ],
            "decisions": [],
            "requirements": [],
            "todos": [],
            "risks": [],
            "open_questions": []
        }
