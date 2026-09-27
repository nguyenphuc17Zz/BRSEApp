"""Deterministic comparison engine: counts, keys, fields, duplicates, encoding,
dates, numerics, referential integrity, status transitions, master codes.

Pure functions over row dicts — no DB, no AI. AI only explains/categorizes later.
"""
import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.qa.data_qa.transforms import (
    apply_transform, normalize_for_compare, values_equal, describe_value,
)

MAX_STORED_DIFFS = 5_000

MOJIBAKE_RE = re.compile(r"[Ã�]|ã\x81|ã\x82|ï¼|ï½|â\x80|â\x82|ã\x80|ã\x81")
HALFWIDTH_KATAKANA_RE = re.compile(r"[\uFF61-\uFF9F]")


def make_key(row: Dict[str, Any], key_fields: List[str]) -> str:
    parts = []
    for f in key_fields:
        v = row.get(f)
        parts.append("__NULL__" if v is None else str(v))
    return "||".join(parts)


def index_by_key(rows: List[Tuple[Dict[str, Any], int]],
                 key_fields: List[str]) -> Tuple[Dict[str, Tuple[Dict[str, Any], int]], Dict[str, int]]:
    index: Dict[str, Tuple[Dict[str, Any], int]] = {}
    dup_counts: Dict[str, int] = {}
    for row, no in rows:
        k = make_key(row, key_fields)
        dup_counts[k] = dup_counts.get(k, 0) + 1
        if k not in index:
            index[k] = (row, no)
    return index, dup_counts


def compare_counts(n_src: int, n_dst: int) -> Dict[str, Any]:
    return {"source": n_src, "dest": n_dst, "diff": n_dst - n_src,
            "match": n_src == n_dst}


def find_missing_extra(src_index: Dict[str, Any], dst_index: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    missing = [k for k in src_index if k not in dst_index]
    extra = [k for k in dst_index if k not in src_index]
    return missing, extra


def compare_fields(src_row: Dict[str, Any], dst_row: Dict[str, Any],
                   mappings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Field-level compare honoring mapping + transform + ignore. Returns mismatches."""
    out = []
    for m in mappings:
        if m.get("ignored"):
            continue
        src_f = m.get("source_field", "")
        dst_f = m.get("dest_field", src_f)
        if not src_f:
            continue
        a = src_row.get(src_f)
        if m.get("transform_json"):
            import json as _json
            try:
                t = _json.loads(m["transform_json"]) if isinstance(m["transform_json"], str) else m["transform_json"]
                a = apply_transform(a, t or {})
            except Exception:
                pass
        b = dst_row.get(dst_f)
        if not values_equal(normalize_for_compare(a), normalize_for_compare(b)):
            out.append({"field": dst_f, "source_field": src_f,
                        "expected": describe_value(a), "actual": describe_value(b)})
    return out


def detect_duplicates(index: Dict[str, Any], dup_counts: Dict[str, int]) -> List[Dict[str, Any]]:
    return [{"key": k, "count": c, "kind": "duplicate_key"}
            for k, c in dup_counts.items() if c > 1]


def detect_possible_duplicates(rows: List[Tuple[Dict[str, Any], int]],
                               combo_fields: List[str]) -> List[Dict[str, Any]]:
    """Same combo (e.g. name+phone+email) but different business key -> possible duplicate."""
    seen: Dict[str, str] = {}
    out = []
    for row, no in rows:
        combo = "||".join(str(row.get(f, "")) for f in combo_fields)
        if not combo.strip(" |"):
            continue
        first = seen.get(combo)
        cur_key = str(row.get("__biz_key__", no))
        if first is not None and first != cur_key:
            out.append({"key": cur_key, "count": 2, "kind": "possible_duplicate",
                        "combo": combo[:200]})
        else:
            seen.setdefault(combo, cur_key)
    return out


def check_encoding(value: Any, field: str = "") -> Optional[Dict[str, Any]]:
    if not isinstance(value, str) or not value:
        return None
    issues = []
    if MOJIBAKE_RE.search(value):
        issues.append("mojibake")
    try:
        value.encode("cp932")
    except UnicodeEncodeError:
        issues.append("unsupported_for_shift_jis")
    # lone surrogates / control chars (keep \n\t\r)
    if any(ord(ch) < 32 and ch not in "\n\t\r" for ch in value):
        issues.append("control_chars")
    if HALFWIDTH_KATAKANA_RE.search(value):
        issues.append("half_width_katakana")
    if not issues:
        return None
    return {"field": field, "issues": issues, "sample": value[:120]}


def script_of(text: str) -> str:
    kinds = set()
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf":
            kinds.add("kanji")
        elif "\u3040" <= ch <= "\u309f":
            kinds.add("hiragana")
        elif "\u30a0" <= ch <= "\u30ff":
            kinds.add("katakana")
        elif ch.isascii() and ch.isalpha():
            kinds.add("latin")
    return "+".join(sorted(kinds)) or "other"


def check_date(value: Any, field: str = "", allow_null: bool = True) -> Optional[Dict[str, Any]]:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None if allow_null else {"field": field, "issue": "null_date"}
    s = str(value).strip()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d", "%d/%m/%Y",
                "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y%m%d%H%M%S"):
        try:
            datetime.strptime(s, fmt)
            return None
        except (ValueError, TypeError):
            continue
    return {"field": field, "issue": "invalid_date", "value": s[:60]}


def check_numeric(value: Any, field: str = "", spec: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None
    spec = spec or {}
    try:
        num = float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return {"field": field, "issue": "not_numeric", "value": str(value)[:60]}
    if "min" in spec and num < spec["min"]:
        return {"field": field, "issue": "below_min", "value": num}
    if "max" in spec and num > spec["max"]:
        return {"field": field, "issue": "above_max", "value": num}
    if spec.get("integer") and not float(num).is_integer():
        return {"field": field, "issue": "not_integer", "value": num}
    if "precision" in spec:
        s = str(value).replace(",", "")
        if "." in s and len(s.split(".")[1]) != spec["precision"]:
            return {"field": field, "issue": "precision_mismatch", "value": s[:60]}
    return None


def severity_for(diff_type: str, field: str = "", context: str = "") -> Tuple[str, str]:
    t = (field or "").lower()
    if diff_type == "missing":
        if any(k in t or k in context.lower() for k in ["order", "受注", "customer", "payment", "決済"]):
            return "HIGH", "Missing business record (order/customer/payment context)"
        return "MEDIUM", "Record present in source but missing in destination"
    if diff_type == "extra":
        return "MEDIUM", "Unexpected record in destination"
    if diff_type == "mismatch":
        if any(k in t for k in ["status", "amount", "total", "price", "ステータス", "金額"]):
            return "HIGH", "Business-critical field mismatch"
        if any(k in t for k in ["name", "名前", "address", "住所"]):
            return "MEDIUM", "Master/display field mismatch"
        return "LOW", "Field value differs"
    if diff_type == "rule_violation":
        return "HIGH", "Business rule violated"
    if diff_type == "duplicate":
        return "HIGH", "Duplicate business key"
    if diff_type == "encoding":
        return "MEDIUM", "Encoding/character issue (JP project risk)"
    return "MEDIUM", "Difference detected"
