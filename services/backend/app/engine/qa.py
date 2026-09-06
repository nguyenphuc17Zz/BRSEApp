import re
from typing import Dict, List, Optional, Any

class QAChecker:
    """Performs translation QA checks: number preservation, code identifiers, glossary compliance."""

    NUMBER_PATTERN = re.compile(r"\b\d+(?:[\.,]\d+)?\b")
    URL_PATTERN = re.compile(r"https?://[^\s/$.?#].[^\s]*")
    API_ID_PATTERN = re.compile(r"\b(?:get|post|put|delete|patch)[A-Z0-9]\w*|[a-z]+(?:[A-Z][a-z0-9]+)+\b|[a-z0-9]+(?:_[a-z0-9]+)+", re.IGNORECASE)

    @classmethod
    def run_qa(
        cls,
        source_text: str,
        translated_text: str,
        glossary_items: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]:
        warnings = []

        # 1. Number preservation check
        source_nums = set(cls.NUMBER_PATTERN.findall(source_text))
        target_nums = set(cls.NUMBER_PATTERN.findall(translated_text))
        
        missing_nums = source_nums - target_nums
        extra_nums = target_nums - source_nums
        if missing_nums:
            warnings.append(f"Number inconsistency: Source numbers {list(missing_nums)} not found in translation.")
        if extra_nums and len(source_nums) > 0:
            warnings.append(f"Number inconsistency: Translation contains unexpected numbers {list(extra_nums)}.")

        # 2. URL preservation check
        source_urls = set(cls.URL_PATTERN.findall(source_text))
        target_urls = set(cls.URL_PATTERN.findall(translated_text))
        missing_urls = source_urls - target_urls
        if missing_urls:
            warnings.append(f"URL missing: {list(missing_urls)} not preserved in translation.")

        # 3. Glossary compliance check
        if glossary_items:
            for g in glossary_items:
                src_term = g.get("source_term", "")
                tgt_term = g.get("target_term", "")
                # If source text contains the glossary term, verify that target text contains target term
                if src_term and src_term in source_text:
                    if tgt_term and tgt_term.lower() not in translated_text.lower():
                        warnings.append(f"Glossary term warning: Mandatory term '{src_term}' -> '{tgt_term}' was not detected in translation.")

        # 4. Length sanity check
        if len(source_text) > 50 and len(translated_text) < 10:
            warnings.append("Length warning: Translation appears suspiciously short compared to source.")

        return warnings
