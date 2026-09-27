"""Data quality rules: UI-built evaluation, AI generation (DRAFT), guarded custom SQL.

Custom SQL runs ONLY against in-memory SQLite built from uploaded snapshots —
never a live database. Single SELECT, deny-listed keywords, row caps.
"""
import json
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from app.qa.api_testing.assertion_engine import evaluate as _assert_eval
from app.qa.data_qa.comparison import check_date, check_numeric

SQL_DENY = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|attach|detach|pragma|"
    r"vacuum|reindex|replace|grant|revoke|call|copy|load_extension|load)\b",
    re.IGNORECASE)
MAX_SQL_ROWS = 10_000


def validate_sql(sql: str) -> str:
    s = (sql or "").strip().rstrip(";").strip()
    if not s:
        raise ValueError("SQL is empty.")
    if ";" in s:
        raise ValueError("Only a single statement is allowed.")
    if not re.match(r"(?is)^\s*(select|with)\b", s):
        raise ValueError("Only SELECT/WITH queries are allowed (read-only).")
    if SQL_DENY.search(s):
        raise ValueError("Blocked keyword in SQL (read-only guard).")
    return s


def run_guarded_sql(rows: List[Dict[str, Any]], sql: str,
                    table: str = "data") -> List[Dict[str, Any]]:
    """Builds in-memory SQLite from snapshot rows, runs guarded SELECT. Violations = returned rows."""
    clean = validate_sql(sql)
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", table):
        raise ValueError("Invalid table name.")
    fields: List[str] = []
    for r in rows:
        for k in (r or {}).keys():
            if k not in fields:
                fields.append(str(k))
    if not fields:
        return []
    cols = ", ".join(f'"{f}" TEXT' for f in fields)
    con = sqlite3.connect(":memory:")
    try:
        con.execute(f'CREATE TABLE "{table}" ({cols})')
        con.executemany(
            f'INSERT INTO "{table}" VALUES ({",".join("?" for _ in fields)})',
            [[None if r.get(f) is None else str(r.get(f)) for f in fields] for r in rows])
        con.execute("SELECT 1")  # sanity
        cur = con.execute(f"SELECT * FROM ({clean}) LIMIT {MAX_SQL_ROWS}")
        names = [d[0] for d in cur.description or []]
        return [dict(zip(names, row)) for row in cur.fetchall()]
    finally:
        con.close()


def _cond(value: Any, condition: str, expect: Any = None) -> bool:
    return _assert_eval({"field": "json", "target": "x", "operator": condition,
                         "expected_value": expect},
                        {"body": {"x": value}})["passed"]


def _parse_date_loose(value: Any):
    from datetime import datetime as _dt
    s = str(value).strip()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d", "%d/%m/%Y",
                "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y%m%d%H%M%S"):
        try:
            return _dt.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _ordered(a: Any, b: Any, rel: str) -> bool:
    """Order comparison that understands dates, numbers, then strings."""
    if rel not in ("lte", "gte", "eq", "ne", "lt", "gt"):
        return True
    da, db = _parse_date_loose(a), _parse_date_loose(b)
    if da is not None and db is not None:
        x, y = da, db
    else:
        try:
            x, y = float(str(a).replace(",", "")), float(str(b).replace(",", ""))
        except (ValueError, TypeError):
            x, y = str(a), str(b)
    return {"lte": x <= y, "gte": x >= y, "eq": x == y,
            "ne": x != y, "lt": x < y, "gt": x > y}[rel]


def eval_rule_on_row(rule_type: str, definition: Dict[str, Any],
                     row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Returns violation dict or None. Row-level rules only (unique/calc handled at dataset level)."""
    d = definition or {}
    if rule_type == "required":
        f = d.get("field", "")
        v = row.get(f)
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return {"field": f, "issue": "required_missing"}
    elif rule_type == "range":
        r = check_numeric(row.get(d.get("field", "")), d.get("field", ""),
                          {"min": d.get("min"), "max": d.get("max"),
                           "integer": d.get("integer", False),
                           **({"precision": d["precision"]} if "precision" in d else {})})
        # strip None bounds
        if r and ((r.get("issue") == "below_min" and d.get("min") is None) or
                  (r.get("issue") == "above_max" and d.get("max") is None)):
            return None
        if r:
            return r
    elif rule_type == "format":
        kind = (d.get("kind") or "date").lower()
        f = d.get("field", "")
        if kind == "date":
            r = check_date(row.get(f), f, allow_null=d.get("allow_null", True))
            if r:
                return r
        elif kind == "email":
            v = str(row.get(f) or "")
            if v and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
                return {"field": f, "issue": "invalid_email", "value": v[:60]}
    elif rule_type == "cross_field":
        cond = d.get("if") or {}
        then = d.get("then") or {}
        if _cond(row.get(cond.get("field")), cond.get("condition", "eq"), cond.get("value")):
            if not _cond(row.get(then.get("field")), then.get("condition", "not_empty"),
                         then.get("value")):
                return {"field": then.get("field"),
                        "issue": f"cross_field: when {cond.get('field')} {cond.get('condition')} "
                                 f"{cond.get('value')}, expected {then.get('field')} "
                                 f"{then.get('condition')} {then.get('value', '')}".strip()}
    elif rule_type == "consistency":
        a, b = row.get(d.get("field_a")), row.get(d.get("field_b"))
        rel = (d.get("relation") or "lte").lower()
        if a is not None and b is not None and str(a).strip() != "" and str(b).strip() != "":
            if not _ordered(a, b, rel):
                return {"field": d.get("field_a"),
                        "issue": f"consistency: {d.get('field_a')} {rel} {d.get('field_b')} failed"}
    return None


def eval_unique(rows: List[Tuple[Dict[str, Any], int]],
                fields: List[str]) -> List[Dict[str, Any]]:
    seen: Dict[str, int] = {}
    out = []
    for row, no in rows:
        k = "||".join(str(row.get(f, "")) for f in fields)
        if k in seen:
            out.append({"key": k, "row_no": no, "issue": "duplicate",
                        "first_row_no": seen[k]})
        else:
            seen[k] = no
    return out


def eval_calculation(headers: List[Dict[str, Any]], details: List[Dict[str, Any]],
                     definition: Dict[str, Any]) -> List[Dict[str, Any]]:
    """header.total == SUM(detail.amount) grouped by key. definition:
    {header_key, header_field, detail_key, detail_field}."""
    from collections import defaultdict
    sums: Dict[str, float] = defaultdict(float)
    for r in details:
        try:
            sums[str(r.get(definition.get("detail_key")))] += float(
                str(r.get(definition.get("detail_field"))).replace(",", ""))
        except (ValueError, TypeError):
            return [{"issue": "non_numeric_detail",
                     "key": str(r.get(definition.get("detail_key")))}]
    out = []
    for h in headers:
        k = str(h.get(definition.get("header_key")))
        try:
            expected = float(str(h.get(definition.get("header_field"))).replace(",", ""))
        except (ValueError, TypeError):
            out.append({"key": k, "issue": "non_numeric_header"})
            continue
        if abs(expected - sums.get(k, 0.0)) > 1e-9:
            out.append({"key": k, "issue": "calculation_mismatch",
                        "expected": expected, "actual": sums.get(k, 0.0)})
    return out


RULE_SYSTEM = (
    "You are a senior QA analyst writing data validation rules. "
    "Propose only rules supported by the requirement evidence. "
    "Mark uncertain ones and keep them minimal and deterministic."
)


async def suggest_rules(requirement_title: str, requirement_desc: str,
                        sample_fields: List[str],
                        preferred_provider: Optional[str] = None,
                        model: Optional[str] = None) -> List[Dict[str, Any]]:
    from app.qa.llm import generate_qa_json
    from app.qa.api_testing import redact as R
    clean_req, _ = R.redact_for_ai({"title": requirement_title, "desc": requirement_desc})
    prompt = f"""Requirement: {json.dumps(clean_req, ensure_ascii=False)[:1000]}
Available fields: {sample_fields[:40]}
Propose data quality rules. Return strict JSON:
{{"rules": [{{"rule_type": "required|unique|range|format|cross_field|consistency|calculation",
"definition": {{...}}, "reason": "..."}}]}}
cross_field definition: {{"if": {{"field": "...", "condition": "eq", "value": "..."}},
"then": {{"field": "...", "condition": "not_empty"}}}}"""
    parsed = await generate_qa_json(prompt, RULE_SYSTEM,
                                    preferred_provider, model, max_tokens=1200)
    raw = parsed.get("rules", []) if isinstance(parsed, dict) else []
    valid = {"required", "unique", "range", "format", "ref_integrity",
             "cross_field", "calculation", "consistency", "mapping", "custom_sql"}
    out = []
    for r in raw[:15]:
        if isinstance(r, dict) and r.get("rule_type") in valid:
            out.append({"rule_type": r["rule_type"],
                        "definition": r.get("definition") or {},
                        "reason": str(r.get("reason") or "")[:300]})
    return out
