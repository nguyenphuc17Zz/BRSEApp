"""Variable resolution for API tests: {{VAR}} substitution, dynamic generators, secrets.

Secrets are decrypted in-memory only at execution time and NEVER written to
evidence, logs, prompts or reports (callers must pass values through redact).
"""
import re
import time
import uuid
from typing import Any, Dict, Tuple

VAR_PATTERN = re.compile(r"\{\{\s*([A-Za-z0-9_.$]+)\s*\}\}")


def dynamic_value(name: str) -> Tuple[bool, str]:
    n = (name or "").lower().lstrip("$")
    if n == "uuid":
        return True, str(uuid.uuid4())
    if n == "timestamp":
        return True, str(int(time.time() * 1000))
    if n in ("email", "test_email"):
        return True, f"qa_{uuid.uuid4().hex[:8]}@example.com"
    if n in ("username", "random_username"):
        return True, f"qa_user_{uuid.uuid4().hex[:6]}"
    if n == "random":
        return True, uuid.uuid4().hex[:8]
    return False, ""


def build_variable_scope(env_vars: Dict[str, Any], env_secrets: Dict[str, str],
                         flow_vars: Dict[str, Any], extra: Dict[str, Any] = None) -> Dict[str, Any]:
    """Merge scopes. Secrets are DECRYPTED values — handle with care, redact before persisting."""
    scope: Dict[str, Any] = {}
    scope.update(env_vars or {})
    scope.update(flow_vars or {})
    scope.update(extra or {})
    scope.update(env_secrets or {})  # secrets win so {{AUTH_TOKEN}} resolves
    return scope


def _lookup(scope: Dict[str, Any], key: str) -> Tuple[bool, Any]:
    if key in scope:
        return True, scope[key]
    # dotted lookup into nested dicts
    cur: Any = scope
    for part in key.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False, None
    return True, cur


def substitute(obj: Any, scope: Dict[str, Any]) -> Tuple[Any, list]:
    """Recursively substitutes {{VAR}}. Returns (resolved, missing_vars). Whole-string {{VAR}} keeps type."""
    missing: list = []
    if isinstance(obj, str):
        m = VAR_PATTERN.fullmatch(obj.strip())
        if m:
            ok, dyn = dynamic_value(m.group(1))
            if ok:
                return dyn, missing
            found, val = _lookup(scope, m.group(1))
            if found:
                return val, missing
            missing.append(m.group(1))
            return obj, missing

        def _rep(match: re.Match) -> str:
            key = match.group(1)
            ok, dyn = dynamic_value(key)
            if ok:
                return dyn
            found, val = _lookup(scope, key)
            if found:
                return str(val)
            missing.append(key)
            return match.group(0)
        return VAR_PATTERN.sub(_rep, obj), missing
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            rk, _ = substitute(k, scope)
            rv, ms = substitute(v, scope)
            missing.extend(ms)
            out[rk] = rv
        return out, sorted(set(missing))
    if isinstance(obj, list):
        out_l = []
        for v in obj:
            rv, ms = substitute(v, scope)
            missing.extend(ms)
            out_l.append(rv)
        return out_l, sorted(set(missing))
    return obj, missing
