"""Assertion evaluation for API tests. Dotted-path JSON access, no extra dependency."""
from typing import Any, Dict, List, Tuple


def get_path(obj: Any, path: str) -> Tuple[bool, Any]:
    """Resolves 'data.user.id' / 'items.0.name'. Returns (found, value)."""
    if not path:
        return True, obj
    cur = obj
    for part in str(path).split("."):
        if isinstance(cur, dict):
            if part in cur:
                cur = cur[part]
            else:
                return False, None
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return False, None
        else:
            return False, None
    return True, cur


def _coerce(value: Any) -> Any:
    if isinstance(value, str):
        s = value.strip()
        if s.lower() in ("null", "none"):
            return None
        if s.lower() == "true":
            return True
        if s.lower() == "false":
            return False
        try:
            return int(s)
        except ValueError:
            pass
        try:
            return float(s)
        except ValueError:
            pass
    return value


def evaluate(assertion: Dict[str, Any], response: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluates one assertion against a response envelope.

    response: {"status_code", "headers", "body", "latency_ms"}
    Returns {"passed", "actual", "message"}.
    """
    field = (assertion.get("field") or "status").lower()
    target = assertion.get("target") or ""
    op = (assertion.get("operator") or "eq").lower()
    expected = _coerce(assertion.get("expected_value"))

    def result(passed: bool, actual: Any, message: str = "") -> Dict[str, Any]:
        return {"passed": passed, "actual": actual,
                "message": message or f"{field}:{target} {op} {expected!r}"}

    if field == "status":
        actual = response.get("status_code")
        exp = int(expected) if str(expected).isdigit() else expected
        if op == "eq":
            return result(actual == exp, actual)
        if op == "ne":
            return result(actual != exp, actual)
        return result(False, actual, f"Unsupported operator for status: {op}")

    if field == "time":
        actual = response.get("latency_ms", 0)
        try:
            exp = float(expected)
        except (TypeError, ValueError):
            return result(False, actual, "Invalid expected time value")
        if op in ("lt", "lte", "gt", "gte", "eq"):
            ok = {"lt": actual < exp, "lte": actual <= exp,
                  "gt": actual > exp, "gte": actual >= exp,
                  "eq": actual == exp}[op]
            return result(ok, actual)
        return result(False, actual, f"Unsupported operator for time: {op}")

    if field == "header":
        headers = {str(k).lower(): v for k, v in (response.get("headers") or {}).items()}
        actual = headers.get(target.lower())
        if op == "exists":
            return result(actual is not None, actual)
        if op == "not_exists":
            return result(actual is None, actual)
        if op == "eq":
            return result(str(actual) == str(expected), actual)
        if op == "contains":
            return result(str(expected) in str(actual or ""), actual)
        return result(False, actual, f"Unsupported operator for header: {op}")

    if field in ("json", "empty"):
        found, actual = get_path(response.get("body"), target)
        if op == "exists":
            return result(found, actual)
        if op == "not_exists":
            return result(not found, actual)
        if op == "empty":
            return result(not found or actual in (None, "", [], {}), actual)
        if op == "not_empty":
            return result(found and actual not in (None, "", [], {}), actual)
        if not found:
            return result(False, None, f"Path not found: {target}")
        if op == "eq":
            return result(actual == expected, actual)
        if op == "ne":
            return result(actual != expected, actual)
        if op == "contains":
            try:
                return result(expected in actual or str(expected) in str(actual), actual)
            except TypeError:
                return result(False, actual)
        if op == "type":
            tmap = {"string": str, "number": (int, float), "integer": int,
                    "boolean": bool, "array": list, "object": dict, "null": type(None)}
            want = tmap.get(str(expected).lower())
            if want is None:
                return result(False, actual, f"Unknown type: {expected}")
            ok = isinstance(actual, want) and not (want is int and isinstance(actual, bool))
            return result(ok, actual)
        if op in ("gt", "gte", "lt", "lte"):
            try:
                a, e = float(actual), float(expected)
            except (TypeError, ValueError):
                return result(False, actual, "Non-numeric comparison")
            ok = {"gt": a > e, "gte": a >= e, "lt": a < e, "lte": a <= e}[op]
            return result(ok, actual)
        return result(False, actual, f"Unsupported operator: {op}")

    return result(False, None, f"Unknown assertion field: {field}")


def evaluate_all(assertions: List[Dict[str, Any]], response: Dict[str, Any]) -> Dict[str, Any]:
    results = []
    for a in assertions:
        r = evaluate(a, response)
        results.append({
            "assertion_id": a.get("id"), "field": a.get("field"),
            "target": a.get("target"), "operator": a.get("operator"),
            "expected": a.get("expected_value"),
            "passed": r["passed"], "actual": r["actual"], "message": r["message"],
        })
    passed = sum(1 for r in results if r["passed"])
    return {"results": results, "passed": passed,
            "failed": len(results) - passed, "all_passed": len(results) > 0 and passed == len(results)}
