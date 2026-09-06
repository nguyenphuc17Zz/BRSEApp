import json
from typing import Dict, List, Any, Optional
from app.core.logging import logger
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response

class SlackReplyGenerator:
    """Generates 4 tailored Japanese reply variations for Slack communications."""

    @classmethod
    async def generate_replies(
        cls,
        current_message: str,
        thread_context: Optional[List[Dict[str, str]]] = None,
        project_name: Optional[str] = None,
        project_rules: Optional[List[str]] = None,
        provider_name: str = "gemini",
        model: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Produces 4 professional reply options (Normal, Polite, Very Polite, Concise)."""
        provider = provider_registry.get_provider(provider_name) or provider_registry.get_provider("gemini")

        thread_str = ""
        if thread_context:
            thread_str = "\n".join([f"- {m.get('sender')}: {m.get('text')}" for m in thread_context[-4:]])

        prompt = f"""You are an expert IT BrSE (Bridge Software Engineer) communicating with Japanese clients on Slack.
Generate 4 distinct, natural Japanese reply candidates to the incoming message.

Incoming Message:
"{current_message}"

Recent Thread Context:
{thread_str if thread_str else "(No prior thread history)"}

Project: {project_name or 'General IT Project'}
Rules: {', '.join(project_rules) if project_rules else 'Follow standard Japanese IT business etiquette.'}

Return JSON with exactly 4 options:
{{
  "replies": [
    {{"style": "Normal", "text": "...", "description": "Standard business response"}},
    {{"style": "Polite", "text": "...", "description": "Respectful teineigo"}},
    {{"style": "Very Polite", "text": "...", "description": "Formal client-facing with keigo"}},
    {{"style": "Concise", "text": "...", "description": "Direct and brief for tech leads"}}
  ]
}}"""

        try:
            resp = await provider.generate(
                prompt=prompt,
                system_instruction="You are a professional Japanese BrSE. Provide natural, accurate, business-ready Slack replies in JSON.",
                model=model,
                temperature=0.3,
                json_mode=True
            )
            data = clean_json_response(resp.text)
            replies = data.get("replies", [])
            if len(replies) >= 4:
                return replies[:4]
        except Exception as e:
            logger.warning(f"AI reply generation fallback: {e}")

        # Fallback reliable options if offline
        return [
            {"style": "Normal", "text": "承知いたしました。確認して折り返しご連絡いたします。", "description": "Standard acknowledgement"},
            {"style": "Polite", "text": "ご連絡ありがとうございます。内容を確認のうえ、迅速に対応いたします。", "description": "Polite confirmation"},
            {"style": "Very Polite", "text": "ご教示いただき誠にありがとうございます。至急チーム内で確認し、進捗をご報告申し上げます。", "description": "Formal client response"},
            {"style": "Concise", "text": "確認しました。対応を進めます。", "description": "Brief internal update"}
        ]
