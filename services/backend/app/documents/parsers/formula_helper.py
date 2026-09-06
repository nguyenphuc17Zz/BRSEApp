import re
from typing import List, Dict, Any, Tuple

# Matches double-quoted string literals in Excel formulas, including escaped double quotes ("")
FORMULA_STRING_REGEX = re.compile(r'"((?:""|[^"])*)"')

# Japanese character range (Hiragana, Katakana, Kanji)
JAPANESE_CHAR_REGEX = re.compile(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')

# Common format specifiers that should NOT be translated (e.g. "yyyy/mm/dd", "#,##0")
FORMAT_SPEC_REGEX = re.compile(r'^[yYmMdDhHsS0#,\.\-: %/\\]+$')


def is_translatable_formula_string(text: str) -> bool:
    """Checks if a string literal extracted from an Excel formula contains natural language."""
    if not text or not text.strip():
        return False

    cleaned = text.strip()

    # Always translate if it contains Japanese characters
    if JAPANESE_CHAR_REGEX.search(cleaned):
        return True

    # Skip pure number/date format patterns
    if FORMAT_SPEC_REGEX.match(cleaned):
        return False

    # Skip if it's purely punctuation or numbers
    if not any(c.isalpha() for c in cleaned):
        return False

    # Skip known Excel internal tokens or single punctuation
    if cleaned.lower() in {"true", "false", "general", "ok", "ng", "error", "#n/a"}:
        # "ok", "ng" might be short, but let's keep it if length > 2 or if Japanese
        if cleaned.lower() in {"true", "false", "general", "#n/a"}:
            return False

    return True


def extract_formula_strings(formula: str) -> List[Dict[str, Any]]:
    """
    Extracts all translatable string literals from an Excel formula.
    Returns list of dicts with:
      - str_index: index among translatable strings
      - start: start character offset in formula
      - end: end character offset in formula
      - raw_match: exact matched string including surrounding quotes
      - text: unescaped text content inside the quotes
    """
    if not formula or not isinstance(formula, str) or not formula.startswith("="):
        return []

    results = []
    str_idx = 0

    for match in FORMULA_STRING_REGEX.finditer(formula):
        content = match.group(1).replace('""', '"')
        if is_translatable_formula_string(content):
            results.append({
                "str_index": str_idx,
                "start": match.start(),
                "end": match.end(),
                "raw_match": match.group(0),
                "text": content
            })
            str_idx += 1

    return results


def replace_formula_strings(formula: str, replacements: Dict[int, str]) -> str:
    """
    Replaces string literals in an Excel formula based on str_index.
    Replacements are applied from right to left to avoid index shifting.
    """
    if not formula or not replacements:
        return formula

    extracted = extract_formula_strings(formula)
    if not extracted:
        return formula

    # Sort in reverse order of start offset
    extracted_sorted = sorted(extracted, key=lambda x: x["start"], reverse=True)

    result = formula
    for item in extracted_sorted:
        idx = item["str_index"]
        if idx in replacements and replacements[idx]:
            new_text = replacements[idx]
            # Escape quotes for Excel formula syntax
            escaped_new = new_text.replace('"', '""')
            quoted_replacement = f'"{escaped_new}"'
            result = result[:item["start"]] + quoted_replacement + result[item["end"]:]

    return result
