from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from app.core.logging import logger

@dataclass
class ContextPackage:
    """Normalized context package fed into the AI Orchestrator across all sources."""
    source_type: str # direct, google_docs, google_sheets, google_slides, slack, desktop_hotkey
    project: Optional[Dict[str, Any]] = None
    project_instructions: List[str] = field(default_factory=list)
    glossary_terms: List[Dict[str, Any]] = field(default_factory=list)
    translation_memory: List[Dict[str, Any]] = field(default_factory=list)
    corrections: List[Dict[str, Any]] = field(default_factory=list)
    slack_context: Optional[Dict[str, Any]] = None
    google_context: Optional[Dict[str, Any]] = None
    desktop_context: Optional[Dict[str, Any]] = None
    estimated_tokens: int = 0

class ContextBudgetManager:
    """Manages token allocation across different context providers to prevent prompt blowout."""

    # Default token budget per context source
    DEFAULT_BUDGETS = {
        "project_instructions": 800,
        "glossary_terms": 500,
        "translation_memory": 600,
        "slack_thread": 1200,
        "google_document": 1000,
        "desktop_window": 200,
        "corrections": 300
    }

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        if not text:
            return 0
        # Fast character heuristic: ~1.5 chars per token for Japanese/Vietnamese mixed text
        return max(1, int(len(text) / 1.8))

    @classmethod
    def trim_to_budget(cls, package: ContextPackage, max_total_tokens: int = 3500) -> ContextPackage:
        """Trims context items based on priority hierarchy:
        Project Rules > Conversation/Thread > Document Headings > Glossary > TM > History.
        """
        current_tokens = 0

        # 1. Project instructions (Highest priority)
        trimmed_instructions = []
        inst_tokens = 0
        for inst in package.project_instructions:
            t = cls.estimate_tokens(inst)
            if inst_tokens + t <= cls.DEFAULT_BUDGETS["project_instructions"]:
                trimmed_instructions.append(inst)
                inst_tokens += t
        package.project_instructions = trimmed_instructions
        current_tokens += inst_tokens

        # 2. Slack Thread / Google context
        if package.slack_context:
            thread_msgs = package.slack_context.get("messages", [])
            # Keep most recent messages up to thread budget
            trimmed_msgs = []
            th_tokens = 0
            for msg in reversed(thread_msgs):
                t = cls.estimate_tokens(msg.get("text", ""))
                if th_tokens + t <= cls.DEFAULT_BUDGETS["slack_thread"]:
                    trimmed_msgs.insert(0, msg)
                    th_tokens += t
                else:
                    break
            package.slack_context["messages"] = trimmed_msgs
            current_tokens += th_tokens

        # 3. Glossary Terms (Conflict resolution: Project terms override global)
        seen_terms = set()
        deduped_glossary = []
        gl_tokens = 0
        # Sort so project terms come first
        sorted_glossary = sorted(package.glossary_terms, key=lambda g: 0 if g.get("scope") == "project" else 1)
        for g in sorted_glossary:
            src = g.get("source_term", "").lower()
            if src in seen_terms:
                continue
            seen_terms.add(src)
            t = cls.estimate_tokens(f"{g.get('source_term')}:{g.get('target_term')}")
            if gl_tokens + t <= cls.DEFAULT_BUDGETS["glossary_terms"]:
                deduped_glossary.append(g)
                gl_tokens += t
        package.glossary_terms = deduped_glossary
        current_tokens += gl_tokens

        # 4. Translation Memory
        trimmed_tm = []
        tm_tokens = 0
        for tm in package.translation_memory:
            t = cls.estimate_tokens(tm.get("source_text", "")) + cls.estimate_tokens(tm.get("target_text", ""))
            if tm_tokens + t <= cls.DEFAULT_BUDGETS["translation_memory"]:
                trimmed_tm.append(tm)
                tm_tokens += t
        package.translation_memory = trimmed_tm
        current_tokens += tm_tokens

        package.estimated_tokens = current_tokens
        return package
