"""Field transforms: date/trim/case/bool/code-map/concat/split. Applied AFTER ignore,
BEFORE comparison. Definitions are data (DRAFT until approved), never code.
"""
import re
from datetime import datetime
from typing import Any, Dict, List


def apply_transform(value: Any, transform: Dict[str, Any]) -> Any:
    op = (transform or {}).get("op", "")
    if op == "trim":
        return value.strip() if isinstance(value, str) else value
    if op == "upper":
        return value.upper() if isinstance(value, str) else value
    if op == "lower":
        return value.lower() if isinstance(value, str) else value
    if op == "date_format":
        return _date_format(value, transform.get("from", ""), transform.get("to", ""))
    if op == "bool_map":
        mapping = transform.get("mapping") or {"1": True, "0": False, "true": True, "false": False}
        key = str(value).strip().lower() if value is not None else ""
        return mapping.get(key, mapping.get(str(value), value))
    if op == "code_map":
        mapping = transform.get("mapping") or {}
        return mapping.get(str(value), transform.get("default", value))
    if op == "concat":
        # {"op": "concat", "fields": ["a", "b"], "sep": " "} — handled at row level
        return value
    if op == "split":
        idx = int(transform.get("index", 0))
        sep = transform.get("sep", ",")
        parts = str(value).split(sep) if value is not None else []
        return parts[idx].strip() if 0 <= idx < len(parts) else None
    if op == "half_width":
        return _to_half_width(value)
    return value


def _date_format(value: Any, fmt_from: str, fmt_to: str) -> Any:
    if value is None or value == "":
        return value
    s = str(value).strip()
    candidates = [fmt_from] if fmt_from else []
    candidates += ["%Y%m%d", "%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
                   "%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S",
                   "%d-%m-%Y", "%Y.%m.%d"]
    for fmt in candidates:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime(fmt_to or "%Y/%m/%d")
        except (ValueError, TypeError):
            continue
    return value


def _to_half_width(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    out = []
    for ch in value:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def normalize_for_compare(value: Any) -> Any:
    """Canonical form WITHOUT collapsing NULL/''/' '/0 — those stay distinct."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if value is None:
        return None
    s = str(value)
    # numeric strings with trailing zeros: "100.00" vs "100" stay distinct (precision matters §26)
    return s


def values_equal(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b if isinstance(a, bool) and isinstance(b, bool) else False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    return str(a) == str(b)


def describe_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, str):
        if value == "":
            return '""(empty)'
        if value.strip() == "":
            return '" "(blank)'
        return value[:200]
    return str(value)[:200]
