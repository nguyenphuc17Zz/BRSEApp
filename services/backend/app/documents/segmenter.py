import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

# Regex patterns for non-translatable tokens that MUST be protected
PROTECTED_PATTERNS = [
    ("URL", re.compile(r"https?://[^\s/$.?#].[^\s]*")),
    ("EMAIL", re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")),
    ("API_PATH", re.compile(r"/(?:api|v[0-9]+|rest|graphql|users|auth|orders|items)(?:/[a-zA-Z0-9_\-]+)+")),
    ("CODE_VAR", re.compile(r"\b[a-z]+(?:[A-Z][a-z0-9]+)+\b")), # camelCase e.g. clientId, accessToken
    ("TICKET_ID", re.compile(r"\b[A-Z]{2,10}-[0-9]{1,6}\b")), # JIRA / Redmine e.g. ABC-104, BUG-42
    ("VERSION", re.compile(r"\bv[0-9]+(?:\.[0-9]+)+(?:-[a-zA-Z0-9]+)?\b")), # e.g. v2.1.0-beta
]

class TokenProtector:
    """Protects URLs, emails, code identifiers, and tickets from modification by replacing with placeholders."""

    @classmethod
    def protect_tokens(cls, text: str) -> Tuple[str, Dict[str, str]]:
        if not text:
            return text, {}

        mapping: Dict[str, str] = {}
        protected_text = text
        token_counter = 1

        for kind, pattern in PROTECTED_PATTERNS:
            matches = list(pattern.finditer(protected_text))
            # Reverse order replacement to maintain string indices
            for match in reversed(matches):
                val = match.group(0)
                # Skip if already a protected token placeholder
                if val.startswith("__PROTECTED_"):
                    continue
                placeholder = f"__PROTECTED_{kind}_{token_counter}__"
                mapping[placeholder] = val
                token_counter += 1
                protected_text = protected_text[:match.start()] + placeholder + protected_text[match.end():]

        return protected_text, mapping

    @classmethod
    def protect(cls, text: str) -> Tuple[str, Dict[str, str]]:
        return cls.protect_tokens(text)

    @classmethod
    def restore_tokens(cls, text: str, mapping: Dict[str, str]) -> Tuple[str, List[str]]:
        """Restores original values into translated text using exact and regex-resilient matching."""
        if not text or not mapping:
            return text, []

        restored = text
        missing_tokens = []

        for placeholder, original_val in mapping.items():
            # 1. Exact match replacement
            if placeholder in restored:
                restored = restored.replace(placeholder, original_val)
                continue

            # 2. Resilient regex replacement (handles markdown wrapping `...`, internal spaces, and casing)
            # Placeholder format: __PROTECTED_<KIND>_<ID>__
            clean_name = placeholder.strip("_")
            parts = clean_name.split("_")
            if len(parts) >= 3:
                # E.g. parts: ['PROTECTED', 'API', 'PATH', '1']
                inner_regex = r"\s*_\s*".join(re.escape(p) for p in parts)
            else:
                inner_regex = re.escape(clean_name)

            pattern = re.compile(
                r"[`*_~]*__\s*" + inner_regex + r"\s*__[`*_~]*",
                re.IGNORECASE
            )

            if pattern.search(restored):
                restored = pattern.sub(original_val, restored)
            else:
                # Token was dropped by AI model
                missing_tokens.append(f"Missing protected token {placeholder} (originally: {original_val})")
                # Fallback append if critical
                restored += f" ({original_val})"

        return restored, missing_tokens

@dataclass
class ParsedSegment:
    """Standardized translatable segment model across DOCX, XLSX, PPTX, and PDF."""
    segment_index: int
    source_text: str
    location: Dict[str, Any] # e.g. {"type": "paragraph", "index": 0} or {"sheet": "Data", "cell": "A1"}
    protected_tokens: Dict[str, str] = field(default_factory=dict)
    context_hint: Optional[str] = None # heading, slide title, or column header
    formatting_meta: Dict[str, Any] = field(default_factory=dict) # bold, italic, font_size, color, etc.
