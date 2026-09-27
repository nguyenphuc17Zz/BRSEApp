"""Centralized secret redaction for API testing.

Single choke point: every request/response stored as evidence, shown in a
report, or sent to an AI provider MUST pass through here first.
"""
import copy
import re
from typing import Any, Dict, Tuple

SENSITIVE_HEADER_NAMES = {
    "authorization", "proxy-authorization", "cookie", "set-cookie",
    "x-api-key", "api-key", "apikey", "x-auth-token", "access-token",
    "refresh-token", "secret", "client-secret",
}
SENSITIVE_FIELD_TOKENS = {
    "password", "passwd", "pwd", "token", "secret", "credential",
    "access_key", "api_key", "apikey", "auth", "authorization",
    "refresh_token", "session", "private_key",
}
REDACTED = "***REDACTED***"


def _is_sensitive_field(name: str) -> bool:
    n = (name or "").lower()
    return any(t in n for t in SENSITIVE_FIELD_TOKENS)


def redact_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (headers or {}).items():
        if (k or "").lower() in SENSITIVE_HEADER_NAMES or _is_sensitive_field(k):
            out[k] = REDACTED
        else:
            out[k] = v
    return out


def redact_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: (REDACTED if _is_sensitive_field(k) else redact_json(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_json(v) for v in obj]
    if isinstance(obj, str) and len(obj) > 200:
        # Long opaque strings (tokens/blobs) — keep shape, drop value
        return f"<{len(obj)} chars redacted>" if re.search(r"[A-Za-z0-9_\-]{32,}", obj) else obj
    return obj


def redact_text(text: str) -> str:
    if not text:
        return text
    # Bearer / Basic credentials in raw text
    red = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.~\+/]+=*", r"\1" + REDACTED, text)
    red = re.sub(r"(?i)(basic\s+)[A-Za-z0-9_\-\.~\+/]+=*", r"\1" + REDACTED, red)
    return red


def redact_request(method: str, url: str, headers: Dict[str, Any],
                   params: Dict[str, Any], body: Any) -> Dict[str, Any]:
    return {
        "method": method, "url": url,
        "headers": redact_headers(headers),
        "params": redact_json(copy.deepcopy(params or {})),
        "body": redact_json(copy.deepcopy(body)) if isinstance(body, (dict, list)) else redact_text(str(body or "")),
    }


def redact_response(status_code: Any, headers: Dict[str, Any], body: Any) -> Dict[str, Any]:
    return {
        "status_code": status_code,
        "headers": redact_headers(headers),
        "body": redact_json(copy.deepcopy(body)) if isinstance(body, (dict, list)) else redact_text(str(body or "")[:8000]),
    }


def redact_for_ai(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """Deep-redact an arbitrary dict before sending to an AI provider. Returns (clean, had_secrets)."""
    import json as _json
    raw = _json.dumps(payload, ensure_ascii=False, default=str)
    had = bool(re.search(r"REDACTED|authorization|password|token|secret", raw, re.IGNORECASE))
    clean = redact_json(copy.deepcopy(payload))
    return clean, had
