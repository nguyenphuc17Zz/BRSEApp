import json
from typing import Dict, List, Optional, Any, Tuple

class PromptBuilder:
    """Builds modular structured prompts for AI translation, explanation, and replies."""

    SYSTEM_COMTOR_ROLE = """You are an elite IT Comtor (IT Communicator) and Bridge Software Engineer (BrSE) specializing in Japanese ↔ Vietnamese software development.
Your translations must be:
- Exceptionally accurate in IT context.
- Consistent with established project terminology and glossaries.
- Natural and appropriate in business register.
- Free of literal machine-translation artifacts.
- Exact in preserving numbers, URLs, endpoints, variables, and code identifiers.

Always respond in strictly valid JSON matching the requested structure."""

    @classmethod
    def build_translation_prompt(
        cls,
        source_text: str,
        source_lang: str,
        target_lang: str,
        context_package: Dict[str, Any],
        style: str = "auto"
    ) -> Tuple[str, str]:
        """
        Returns (system_instruction, user_prompt).
        """
        prompt_sections = []

        # 1. Project Context
        project = context_package.get("project")
        if project:
            prompt_sections.append(f"### CURRENT PROJECT CONTEXT\nProject Name: {project.get('name')}\nClient: {project.get('client') or 'N/A'}\nDescription: {project.get('description') or 'N/A'}")

        # 2. Project Instructions / Rules
        instructions = context_package.get("project_instructions", [])
        if instructions:
            rules_str = "\n".join(f"- {rule}" for rule in instructions)
            prompt_sections.append(f"### MANDATORY PROJECT RULES\n{rules_str}")

        # 3. Glossary Constraints
        glossary = context_package.get("glossary_terms", [])
        if glossary:
            terms_str = "\n".join(f"- \"{t['source_term']}\" MUST BE TRANSLATED AS \"{t['target_term']}\" (Category: {t.get('category', 'IT')})" for t in glossary)
            prompt_sections.append(f"### MANDATORY GLOSSARY MAPPING (MUST APPLY)\n{terms_str}")

        # 4. Translation Memory (Reference only)
        tm = context_package.get("translation_memory", [])
        if tm:
            tm_str = "\n".join(f"- Reference Source: \"{item['source_text']}\" -> Reference Translation: \"{item['target_text']}\" (Similarity: {item.get('similarity', 1.0)})" for item in tm)
            prompt_sections.append(f"### TRANSLATION MEMORY REFERENCES (Adapt naturally)\n{tm_str}")

        # 5. User Corrections
        corrections = context_package.get("corrections", [])
        if corrections:
            corr_str = "\n".join(f"- When translating: \"{c['source_text']}\", User previously corrected \"{c['original_translation']}\" to prefer: \"{c['corrected_translation']}\"" for c in corrections)
            prompt_sections.append(f"### USER HISTORICAL CORRECTIONS (Priority)\n{corr_str}")

        # 6. Style Instruction
        target_style = style if style and style != "auto" else "business"
        prompt_sections.append(f"### TARGET STYLE & REGISTER\nTarget Register: {target_style}\nRule: If source is Japanese business email/chat, use polite business Vietnamese (e.g. 'Vui lòng xác nhận' instead of 'Hãy kiểm tra'). Keep API names, code identifiers, and parameters unaltered.")

        # 7. Ambiguity Handling Instruction
        prompt_sections.append("""### AMBIGUITY HANDLING
If the source sentence contains multiple valid technical or business interpretations (e.g., '対象外' can mean 'out of scope', 'not applicable', or 'excluded from test cases'), return 2 to 3 candidate options in the translations array, each with its register, confidence score, and rationale.
If the sentence is straightforward, 1 high-confidence translation is sufficient.""")

        # 8. Source Text to translate
        prompt_sections.append(f"### SOURCE TEXT TO TRANSLATE ({source_lang.upper()} -> {target_lang.upper()}):\n\"\"\"\n{source_text}\n\"\"\"")

        # 9. JSON Output Schema
        schema_instruction = """### OUTPUT FORMAT (JSON ONLY)
Return a valid JSON object with EXACTLY this structure:
{
  "source_language": "string (e.g. ja)",
  "target_language": "string (e.g. vi)",
  "translations": [
    {
      "text": "translated sentence",
      "style": "business | natural | technical | very_polite | casual | concise",
      "confidence": 0.95,
      "reason": "explanation of this interpretation or null"
    }
  ],
  "ambiguity_detected": false,
  "ambiguity_reason": "explanation if ambiguity detected, else null",
  "detected_terms": [
    {"source": "IT term in source", "suggested": "meaning in target"}
  ],
  "used_glossary_terms": ["list of source terms applied"]
}"""
        prompt_sections.append(schema_instruction)

        user_prompt = "\n\n".join(prompt_sections)
        return cls.SYSTEM_COMTOR_ROLE, user_prompt

    @classmethod
    def build_explain_prompt(cls, source_text: str, translation_text: str, source_lang: str, target_lang: str) -> Tuple[str, str]:
        prompt = f"""Explain the following translation for an IT Comtor / BrSE:
Source ({source_lang}): "{source_text}"
Translation ({target_lang}): "{translation_text}"

Return JSON matching:
{{
  "summary": "Concise summary of meaning and context",
  "grammar_and_nuances": ["nuance 1", "grammar point 2"],
  "technical_terms": [
    {{"term": "term name", "explanation": "role in IT development"}}
  ],
  "alternative_interpretations": ["alternative nuance 1"]
}}"""
        return cls.SYSTEM_COMTOR_ROLE, prompt

    @classmethod
    def build_reply_prompt(
        cls,
        source_message: str,
        history: Optional[List[str]],
        reply_lang: str,
        user_intent: Optional[str] = None
    ) -> Tuple[str, str]:
        history_str = "\n".join(f"- {h}" for h in (history or []))
        intent_instruction = ""
        if user_intent and user_intent.strip():
            intent_instruction = f"""
CRITICAL USER INTENTION / KEY POINTS TO CONVEY:
The user explicitly wants to express the following points in the reply (may be in Vietnamese or Japanese):
\"\"\"{user_intent.strip()}\"\"\"
Rule: You MUST incorporate and accurately translate this intention/factual details (dates, times, causes, team status) into all Japanese reply options while polishing them into professional business Japanese.
"""
        prompt = f"""Generate professional reply suggestions for an IT Comtor / BrSE responding to the Japanese client/team.
Context history:
{history_str if history_str else "N/A"}

Source message received:
"{source_message}"
{intent_instruction}
Generate reply options in {reply_lang} across styles (normal polite, very polite, concise confirmation, natural explanation).
Return JSON matching:
{{
  "options": [
    {{
      "style": "polite | very_polite | concise | natural",
      "text": "reply content in {reply_lang}",
      "notes": "when to use this option"
    }}
  ]
}}"""
        return cls.SYSTEM_COMTOR_ROLE, prompt

    @classmethod
    def build_rewrite_prompt(cls, text: str, tone: str, lang: str) -> Tuple[str, str]:
        prompt = f"""Rewrite the following text to have tone: '{tone}' while strictly preserving original technical meaning and facts.
Text ({lang}):
"{text}"

Return JSON:
{{
  "original_text": "{text}",
  "rewritten_text": "transformed text",
  "tone": "{tone}"
}}"""
        return cls.SYSTEM_COMTOR_ROLE, prompt
