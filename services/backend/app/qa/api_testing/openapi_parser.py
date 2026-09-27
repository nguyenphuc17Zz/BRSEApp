"""Deterministic OpenAPI import: parse JSON/YAML without AI. AI is only used later
for business context, test design, assertions and gap detection."""
import json
from typing import Any, Dict, List, Tuple

MAX_SPEC_BYTES = 5 * 1024 * 1024


def load_spec(raw_text: str) -> Tuple[Dict[str, Any], str]:
    """Parses OpenAPI from JSON or YAML text. Returns (spec, format). Raises ValueError."""
    if not raw_text or len(raw_text.encode("utf-8")) > MAX_SPEC_BYTES:
        raise ValueError("Empty spec or spec exceeds 5MB limit.")
    text = raw_text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text), "json"
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid OpenAPI JSON: {e}")
    try:
        import yaml
    except ImportError:
        raise ValueError("YAML support requires pyyaml. Paste JSON instead.")
    try:
        doc = yaml.safe_load(text)
    except Exception as e:
        raise ValueError(f"Invalid OpenAPI YAML: {e}")
    if not isinstance(doc, dict):
        raise ValueError("OpenAPI document must be an object.")
    return doc, "yaml"


def _ref_hint(schema: Any) -> str:
    if isinstance(schema, dict) and "$ref" in schema:
        return str(schema["$ref"]).split("/")[-1]
    return ""


def parse_openapi(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts endpoints, auth, version from a parsed OpenAPI 2.x/3.x document."""
    info = spec.get("info") or {}
    version = str(info.get("version") or "v1")
    title = str(info.get("title") or "")
    security_defs = spec.get("components", {}).get("securitySchemes", {}) or spec.get("securityDefinitions", {}) or {}
    global_security = spec.get("security", [])
    paths = spec.get("paths") or {}

    endpoints: List[Dict[str, Any]] = []
    methods = ("get", "post", "put", "patch", "delete", "head", "options")
    for path, ops in paths.items():
        if not isinstance(ops, dict):
            continue
        for method, op in ops.items():
            if method.lower() not in methods or not isinstance(op, dict):
                continue
            params = op.get("parameters", []) or []
            req_body = op.get("requestBody", {}) or op.get("consumes") or {}
            responses = op.get("responses", {}) or {}
            op_security = op.get("security", global_security)
            auth_type = "none"
            if op_security:
                names = set()
                for req in op_security:
                    if isinstance(req, dict):
                        names.update(req.keys())
                for n in names:
                    scheme = security_defs.get(n, {})
                    stype = str(scheme.get("type", "")).lower()
                    sname = str(scheme.get("name", "")).lower()
                    if stype in ("http",) and str(scheme.get("scheme", "")).lower() == "bearer":
                        auth_type = "bearer"
                    elif stype == "apikey" or "api" in sname and "key" in sname or n.lower() in ("api_key", "apikey"):
                        auth_type = "api_key"
                    elif stype == "http":
                        auth_type = "basic"
                    elif stype in ("oauth2", "openidconnect"):
                        auth_type = "bearer"
                    if auth_type != "none":
                        break
            endpoints.append({
                "method": method.upper(), "path": path,
                "name": str(op.get("summary") or op.get("operationId") or f"{method.upper()} {path}"),
                "description": str(op.get("description") or ""),
                "auth_type": auth_type,
                "parameters": params if isinstance(params, list) else [],
                "request_body": req_body if isinstance(req_body, dict) else {},
                "responses": responses if isinstance(responses, dict) else {},
                "tags": op.get("tags", []) or [],
                "operation_id": str(op.get("operationId") or ""),
            })
    return {"title": title, "version": version, "endpoints": endpoints,
            "auth_schemes": list(security_defs.keys())}


def diff_spec(old_eps: List[Dict[str, Any]], new_parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Compares endpoint signatures (method+path+params+responses keys) for change flags."""
    def sig(e: Dict[str, Any]) -> str:
        params = ",".join(sorted(
            f"{p.get('name')}:{p.get('in')}" for p in (e.get("parameters") or []) if isinstance(p, dict)))
        resps = ",".join(sorted(str(k) for k in (e.get("responses") or {}).keys()))
        return f"{e.get('method')} {e.get('path')} | {params} | {resps} | {e.get('auth_type')}"
    old_map = {f"{e.get('method')} {e.get('path')}": sig(e) for e in old_eps}
    changed, added = [], []
    for e in new_parsed.get("endpoints", []):
        key = f"{e.get('method')} {e.get('path')}"
        if key not in old_map:
            added.append(key)
        elif old_map[key] != sig(e):
            changed.append(key)
    removed = [k for k in old_map if k not in {f"{e.get('method')} {e.get('path')}" for e in new_parsed.get("endpoints", [])}]
    return {"added": added, "changed": changed, "removed": removed}
