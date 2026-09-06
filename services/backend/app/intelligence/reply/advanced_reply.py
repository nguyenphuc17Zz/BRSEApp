import json
from typing import Dict, List, Any, Optional
from app.core.logging import logger
from app.providers.registry import provider_registry
from app.engine.pipeline import clean_json_response

class AdvancedReplyEngine:
    """Intent-driven Japanese reply generator with strict fact checking and commitment protection."""

    @classmethod
    async def generate_smart_replies(
        cls,
        incoming_message: str,
        conversation_history: Optional[List[str]] = None,
        project_name: Optional[str] = None,
        confirmed_decisions: Optional[List[str]] = None,
        rag_chunks: Optional[List[Dict[str, Any]]] = None,
        provider_name: str = "auto",
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        target_prov = provider_name if provider_name and provider_name != "auto" else "groq"
        provider = provider_registry.get_provider(target_prov) or provider_registry.get_provider("groq") or provider_registry.get_provider("gemini")

        decisions_str = "\n".join([f"- {d}" for d in (confirmed_decisions or [])])
        hist_str = "\n".join([f"- {h}" for h in (conversation_history or [])[-3:]])
        
        # Format RAG chunks
        rag_str = ""
        rag_sources = []
        if rag_chunks:
            formatted_chunks = []
            for c in rag_chunks:
                fn = c.get("file_name", "Spec")
                idx = c.get("chunk_index", 1)
                snippet = c.get("text", "")[:350]
                formatted_chunks.append(f"[{fn} #Đoạn {idx}]:\n{snippet}")
                rag_sources.append({
                    "file_name": fn,
                    "chunk_index": idx,
                    "snippet": snippet[:150]
                })
            rag_str = "\n\n".join(formatted_chunks)

        prompt = f"""You are an elite IT BrSE communicating with Japanese clients and product managers.
Analyze the incoming message, determine the primary intent required, and generate 3 professional Japanese reply options.

CRITICAL SAFETY & FACT PROTECTION RULES:
1. SPEC GROUNDING: If Project Specifications or Confirmed Decisions contain the exact answer, technical parameters, or business rules, explain them accurately and politely in Japanese.
2. NEVER fabricate commitments or unconfirmed deadlines (e.g. if asked "Can this be done by tomorrow?", do NOT promise completion unless confirmed in project decisions; instead acknowledge and state you will confirm with the dev team: 確認保留).
3. Do NOT invent people, features, or approvals.
4. Adhere strictly to Japanese IT business etiquette (丁寧語 / 謙譲語 / 敬語).

Incoming Message:
"{incoming_message}"

Conversation Context:
{hist_str if hist_str else "(No prior history)"}

Confirmed Project Decisions:
{decisions_str if decisions_str else "(No confirmed decisions regarding this topic)"}

Project Specifications Context (from Document RAG):
{rag_str if rag_str else "(No relevant project document specifications found)"}

Return JSON matching:
{{
  "detected_intent": "ACKNOWLEDGE / ANSWER / ASK_CLARIFICATION / CONFIRM / NEGOTIATE / REQUEST_TIME / APOLOGIZE",
  "commitment_warning": "Warning text if user should be cautious about promising deadlines, or null",
  "replies": [
    {{
      "style": "Standard Polite (丁寧語)",
      "text": "Japanese text...",
      "rationale": "Why this response is suitable"
    }},
    {{
      "style": "Formal Client-Facing (敬語・謙譲語)",
      "text": "Japanese text...",
      "rationale": "High formality for clients/executives"
    }},
    {{
      "style": "Propose Time/Investigation (確認・回答保留)",
      "text": "Japanese text...",
      "rationale": "Safely defers commitment while checking with team"
    }}
  ]
}}"""

        try:
            resp = await provider.generate(
                prompt=prompt,
                system_instruction="You are a professional IT BrSE. Generate safe, nuanced, commitment-protected Japanese business replies in strict JSON.",
                model=model,
                temperature=0.2,
                json_mode=True
            )
            parsed = clean_json_response(resp.text)
            if "replies" in parsed and len(parsed["replies"]) >= 2:
                parsed["rag_sources"] = rag_sources
                return parsed
        except Exception as e:
            logger.warning(f"Advanced reply error: {e}")

        # Safe fallback
        return {
            "detected_intent": "ACKNOWLEDGE",
            "commitment_warning": "Deadline requested. Verify with team before committing.",
            "replies": [
                {
                    "style": "Standard Polite (丁寧語)",
                    "text": "ご連絡ありがとうございます。内容を確認のうえ、迅速に対応いたします。",
                    "rationale": "Standard polite acknowledgement"
                },
                {
                    "style": "Formal Client-Facing (敬語)",
                    "text": "ご教示いただき誠にありがとうございます。チーム内で確認のうえ、進捗をご報告申し上げます。",
                    "rationale": "Formal respectful response"
                },
                {
                    "style": "Propose Time/Investigation (確認保留)",
                    "text": "確認いたしました。対応可否およびスケジュールを開発チームと確認し、本日中に改めてご連絡いたします。",
                    "rationale": "Safely prevents uncommitted promises"
                }
            ]
        }
