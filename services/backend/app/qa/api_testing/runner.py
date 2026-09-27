"""Synchronous sequential API runner. Correctness + traceability first (no distributed runner).

Every execution writes into Phase 2 TestExecution/TestEvidence. Standalone runs
(without a run_id) get an ad-hoc TestRun so history is never orphaned.
"""
import datetime
import json
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.core.security import decrypt_credential
from app.qa.models import TestCase
from app.qa.api_models import APIEnvironment, APITestConfig, APIAssertion, APITestFlow
from app.qa.execution_models import TestRun, TestExecution, TestEvidence
from app.qa import execution_engines as X
from app.qa.api_testing import redact as R
from app.qa.api_testing import variables as V

MAX_SUITE_SIZE = 50
PROD_NAMES = {"PROD", "PRODUCTION", "LIVE"}
DESTRUCTIVE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _loads(text: str, default: Any) -> Any:
    try:
        return json.loads(text or "") if (text or "").strip() else default
    except Exception:
        return default


def decrypt_env_secrets(env: APIEnvironment) -> Dict[str, str]:
    raw = _loads(env.secrets_json, {})
    return {k: decrypt_credential(v) for k, v in (raw or {}).items()}


def is_prod_env(env: APIEnvironment) -> bool:
    name = (env.name or "").strip().upper()
    if name in PROD_NAMES:
        return True
    return "prod" in (env.base_url or "").lower() and "staging" not in (env.base_url or "").lower()


def resolve_inputs(config: APITestConfig, env: APIEnvironment,
                   flow_vars: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Builds concrete method/url/headers/query/body. Returns (inputs, missing_vars)."""
    secrets = decrypt_env_secrets(env)
    scope = V.build_variable_scope(_loads(env.variables_json, {}), secrets, flow_vars or {})
    url_t, m1 = V.substitute(config.url_template or "", scope)
    if "{{BASE_URL}}" in (config.url_template or "") and "BASE_URL" not in scope:
        scope = dict(scope)
        scope["BASE_URL"] = (env.base_url or "").rstrip("/")
        url_t, m1 = V.substitute(config.url_template or "", scope)
    headers, m2 = V.substitute(_loads(config.headers_json, {}), scope)
    query, m3 = V.substitute(_loads(config.query_json, {}), scope)
    path_params, m4 = V.substitute(_loads(config.path_params_json, {}), scope)
    body_raw, m5 = V.substitute(config.body_text or "", scope)
    # path params into URL
    url = str(url_t)
    if isinstance(path_params, dict):
        for k, v in path_params.items():
            url = url.replace("{" + str(k) + "}", str(v))
    # auth injection (values stay in-memory; redacted before persist)
    auth = _loads(config.auth_ref_json, {})
    atype = (auth.get("type") or "none").lower()
    headers = dict(headers or {})
    if atype == "bearer" and auth.get("secret_key"):
        _, token = V._lookup(scope, auth["secret_key"])
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
    elif atype == "api_key" and auth.get("secret_key"):
        _, key = V._lookup(scope, auth["secret_key"])
        if key is not None:
            headers[auth.get("header") or "X-API-Key"] = key
    elif atype == "basic":
        import base64 as _b64
        _, u = V._lookup(scope, auth.get("username_key") or "BASIC_USER")
        _, p = V._lookup(scope, auth.get("secret_key") or "BASIC_PASS")
        if u is not None and p is not None:
            headers["Authorization"] = "Basic " + _b64.b64encode(f"{u}:{p}".encode()).decode()
    missing = sorted(set(m1 + m2 + m3 + m4 + m5))
    return {"method": (config.method or "GET").upper(), "url": url,
            "headers": headers, "query": query or {}, "body_raw": body_raw}, missing


def _parse_body(text: str, content_type: str) -> Any:
    if not text:
        return None
    if "json" in (content_type or "") or (text.strip().startswith("{") or text.strip().startswith("[")):
        try:
            return json.loads(text)
        except Exception:
            return text
    return text


def classify_error(kind: str, detail: str = "") -> str:
    mapping = {
        "network": "Network Error", "timeout": "Timeout", "dns": "Environment Error (DNS)",
        "config": "Invalid Test Configuration", "auth": "Authentication Failure",
        "assertion": "Assertion Failure", "app": "Application Response Failure",
    }
    return mapping.get(kind, "Unknown")


async def _get_or_create_adhoc_run(db: AsyncSession, project_id: str, build: str = "") -> TestRun:
    run = TestRun(project_id=project_id, run_code=await X.next_run_code(db, project_id),
                  name=f"Ad-hoc API {datetime.datetime.utcnow().strftime('%Y/%m/%d %H:%M')}",
                  version_build=build or "", environment="", status="IN_PROGRESS",
                  scope_json=json.dumps({"adhoc": True, "type": "API"}, ensure_ascii=False))
    db.add(run)
    await db.flush()
    return run


async def execute_api_case(
    db: AsyncSession, test_case_id: str, environment_id: str,
    flow_vars: Optional[Dict[str, Any]] = None, test_run_id: Optional[str] = None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
    changed_by: str = "user", confirm_prod: bool = False,
) -> Dict[str, Any]:
    """Runs one API test case end-to-end. Returns full result envelope."""
    tc = (await db.execute(select(TestCase).where(TestCase.id == test_case_id))).scalars().first()
    if not tc:
        raise ValueError("Test case not found")
    config = (await db.execute(select(APITestConfig).where(
        APITestConfig.test_case_id == test_case_id))).scalars().first()
    if not config:
        raise ValueError("No API config for this test case (not an API test).")
    env = (await db.execute(select(APIEnvironment).where(
        APIEnvironment.id == environment_id))).scalars().first()
    if not env:
        raise ValueError("Environment not found")
    if tc.project_id != env.project_id:
        raise ValueError("Environment belongs to another project.")
    if is_prod_env(env) and config.method.upper() in DESTRUCTIVE_METHODS and not confirm_prod:
        raise ValueError("ProductionGuard: destructive API on PROD needs explicit confirmation.")

    inputs, missing = resolve_inputs(config, env, flow_vars or {})
    if missing:
        raise ValueError(f"Invalid Test Configuration: unresolved variables {missing}.")

    # execution row (Phase 2)
    run_id = test_run_id
    if not run_id:
        adhoc = await _get_or_create_adhoc_run(db, tc.project_id)
        run_id = adhoc.id
    ex = TestExecution(test_run_id=run_id, test_case_id=tc.id,
                       requirement_id=tc.requirement_id,
                       acceptance_criterion_id=tc.acceptance_criterion_id,
                       attempt_no=1, status="RUNNING",
                       case_snapshot_json=json.dumps(
                           {"tc_code": tc.tc_code, "title": tc.title,
                            "expected_result": tc.expected_result}, ensure_ascii=False))
    db.add(ex)
    await db.flush()
    await X.log_history(db, ex.id, "status", "NOT_RUN", "RUNNING", changed_by)

    envelope: Dict[str, Any] = {"error_kind": None, "error_detail": ""}
    started = datetime.datetime.utcnow()
    latency_ms = 0
    try:
        body_text = inputs["body_raw"]
        req_kwargs: Dict[str, Any] = {"headers": inputs["headers"], "params": inputs["query"]}
        ctype = inputs["headers"].get("Content-Type", "application/json")
        if body_text and "json" in ctype:
            try:
                req_kwargs["json"] = json.loads(body_text)
            except Exception:
                req_kwargs["content"] = body_text.encode()
        elif body_text:
            req_kwargs["content"] = body_text.encode() if isinstance(body_text, str) else body_text
        attempts = 2 if config.retry_network else 1
        resp = None
        last_err = None
        for _ in range(attempts):
            try:
                async with httpx.AsyncClient(transport=transport, timeout=config.timeout_s or 30,
                                             follow_redirects=True) as client:
                    resp = await client.request(inputs["method"], inputs["url"], **req_kwargs)
                last_err = None
                break
            except httpx.TimeoutException as e:
                last_err = ("timeout", str(e))
            except httpx.ConnectError as e:
                last_err = ("network", str(e))
                if "dns" in str(e).lower() or "name" in str(e).lower():
                    last_err = ("dns", str(e))
        latency_ms = int((datetime.datetime.utcnow() - started).total_seconds() * 1000)
        if resp is None:
            kind, detail = last_err or ("network", "No response")
            envelope.update({"error_kind": kind, "error_detail": detail[:500]})
            resp_data = {"status_code": None, "headers": {}, "body": None, "latency_ms": latency_ms}
        else:
            resp_headers = dict(resp.headers)
            resp_data = {"status_code": resp.status_code, "headers": resp_headers,
                         "body": _parse_body(resp.text or "", resp_headers.get("content-type", "")),
                         "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = int((datetime.datetime.utcnow() - started).total_seconds() * 1000)
        envelope.update({"error_kind": "network", "error_detail": str(e)[:500]})
        resp_data = {"status_code": None, "headers": {}, "body": None, "latency_ms": latency_ms}
    envelope["response"] = resp_data
    envelope["latency_ms"] = latency_ms

    # assertions: implicit expected_status + APPROVED rows only (DRAFT never auto-counts)
    assertions = (await db.execute(select(APIAssertion).where(
        APIAssertion.test_case_id == tc.id, APIAssertion.status == "APPROVED"))).scalars().all()
    from app.qa.api_testing.assertion_engine import evaluate_all
    checks = [{"field": "status", "target": "", "operator": "eq",
               "expected_value": str(config.expected_status)}]
    checks += [{"id": a.id, "field": a.field, "target": a.target,
                "operator": a.operator, "expected_value": a.expected_value} for a in assertions]
    eval_out = evaluate_all(checks, resp_data)

    if envelope["error_kind"]:
        final_status = "FAIL"
        fail_reason = f"{classify_error(envelope['error_kind'])}: {envelope['error_detail']}"
    elif eval_out["all_passed"]:
        final_status = "PASS"
        fail_reason = None
    else:
        final_status = "FAIL"
        first = next((r for r in eval_out["results"] if not r["passed"]), {})
        fail_reason = f"Assertion Failure: {first.get('message', '')}"

    # persist execution result (Phase 2 path: FAIL requires actual_result — use fail summary)
    actual_text = json.dumps({"status_code": resp_data["status_code"],
                              "failed_assertions": [r for r in eval_out["results"] if not r["passed"]],
                              "latency_ms": latency_ms}, ensure_ascii=False, default=str)[:4000]
    ex.status = final_status
    ex.actual_result = f"PASS: all {len(checks)} assertion(s) passed in {latency_ms}ms." if final_status == "PASS" else actual_text
    ex.fail_reason = fail_reason
    ex.tester = changed_by
    ex.executed_at = datetime.datetime.utcnow()
    await db.flush()
    await X.log_history(db, ex.id, "status", "RUNNING", final_status, changed_by)

    # evidence (redacted)
    req_ev = R.redact_request(inputs["method"], inputs["url"], inputs["headers"],
                              inputs["query"], _parse_body(inputs["body_raw"], inputs["headers"].get("Content-Type", "")))
    resp_ev = R.redact_response(resp_data["status_code"], resp_data["headers"], resp_data["body"])
    db.add(TestEvidence(execution_id=ex.id, test_case_id=tc.id, requirement_id=tc.requirement_id,
                        evidence_type="api_request", title=f"{inputs['method']} {inputs['url']}"[:255],
                        text_content=json.dumps(req_ev, ensure_ascii=False, default=str)[:12000],
                        created_by=changed_by))
    db.add(TestEvidence(execution_id=ex.id, test_case_id=tc.id, requirement_id=tc.requirement_id,
                        evidence_type="api_response",
                        title=f"Response {resp_data['status_code']} in {latency_ms}ms"[:255],
                        text_content=json.dumps({**resp_ev, "latency_ms": latency_ms,
                                                 "assertions": eval_out["results"]},
                                                ensure_ascii=False, default=str)[:20000],
                        created_by=changed_by))
    await db.flush()

    # extracts → flow vars
    new_vars: Dict[str, Any] = {}
    extract_map = _loads(config.extract_map_json, {})
    if isinstance(extract_map, dict) and resp_data["body"] is not None:
        from app.qa.api_testing.assertion_engine import get_path
        for var_name, path in extract_map.items():
            found, val = get_path(resp_data["body"], path)
            if found:
                new_vars[var_name] = val

    run = (await db.execute(select(TestRun).where(TestRun.id == run_id))).scalars().first()
    if run and run.status in ("READY", "DRAFT"):
        run.status = "IN_PROGRESS"
        await db.flush()
    await X.refresh_exec_coverage(db, tc.requirement_id)
    await db.commit()
    await db.refresh(ex)

    return {"execution_id": ex.id, "test_run_id": run_id, "status": final_status,
            "fail_reason": fail_reason, "latency_ms": latency_ms,
            "assertions": eval_out, "response": resp_ev,
            "request": req_ev, "extracted": new_vars,
            "error_kind": envelope["error_kind"],
            "error_label": classify_error(envelope["error_kind"]) if envelope["error_kind"] else None}


async def run_api_suite(
    db: AsyncSession, test_case_ids: List[str], environment_id: str,
    test_run_id: Optional[str] = None, transport: Optional[httpx.AsyncBaseTransport] = None,
    changed_by: str = "user", confirm_prod: bool = False,
    flow_vars: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Sequential suite run (cap 50). Shares extract vars across cases (response chaining)."""
    ids = (test_case_ids or [])[:MAX_SUITE_SIZE]
    shared = dict(flow_vars or {})
    # One shared run for the whole suite (no orphan ad-hoc runs per case)
    suite_run_id = test_run_id
    if not suite_run_id and ids:
        first = (await db.execute(select(TestCase).where(TestCase.id == ids[0]))).scalars().first()
        if not first:
            raise ValueError("Test case not found")
        adhoc = await _get_or_create_adhoc_run(db, first.project_id)
        suite_run_id = adhoc.id
    results = []
    for cid in ids:
        try:
            out = await execute_api_case(db, cid, environment_id, shared, suite_run_id,
                                         transport, changed_by, confirm_prod)
            shared.update(out.get("extracted") or {})
            results.append({"test_case_id": cid, "status": out["status"],
                            "execution_id": out["execution_id"],
                            "latency_ms": out["latency_ms"],
                            "fail_reason": out.get("fail_reason")})
        except ValueError as e:
            results.append({"test_case_id": cid, "status": "BLOCKED",
                            "fail_reason": f"Invalid Test Configuration: {e}"})
        except Exception as e:
            logger.warning(f"Suite case {cid} error: {e}")
            results.append({"test_case_id": cid, "status": "FAIL",
                            "fail_reason": f"Unknown: {e}"})
    tally = {"total": len(results), "pass": sum(1 for r in results if r["status"] == "PASS"),
             "fail": sum(1 for r in results if r["status"] == "FAIL"),
             "blocked": sum(1 for r in results if r["status"] == "BLOCKED")}
    return {"results": results, "test_run_id": suite_run_id,
            **tally, "truncated": len(test_case_ids or []) > MAX_SUITE_SIZE}


async def run_api_flow(
    db: AsyncSession, flow_id: str, environment_id: str,
    test_run_id: Optional[str] = None, transport: Optional[httpx.AsyncBaseTransport] = None,
    changed_by: str = "user", confirm_prod: bool = False,
) -> Dict[str, Any]:
    """Minimal flow: setup → ordered steps (chained vars) → cleanup (fail reported separately)."""
    flow = (await db.execute(select(APITestFlow).where(APITestFlow.id == flow_id))).scalars().first()
    if not flow:
        raise ValueError("Flow not found")
    steps = _loads(flow.step_case_ids_json, [])
    ordered = ([flow.setup_case_id] if flow.setup_case_id else []) + (steps or [])
    out = await run_api_suite(db, ordered, environment_id, test_run_id, transport,
                              changed_by, confirm_prod)
    cleanup_out = None
    if flow.cleanup_case_id:
        try:
            cleanup_out = await execute_api_case(db, flow.cleanup_case_id, environment_id,
                                                 {}, out.get("test_run_id"),
                                                 transport=transport, changed_by=changed_by,
                                                 confirm_prod=confirm_prod)
        except Exception as e:
            cleanup_out = {"status": "FAIL", "fail_reason": f"Cleanup failed separately: {e}"}
    out["cleanup"] = ({"status": cleanup_out.get("status"),
                       "fail_reason": cleanup_out.get("fail_reason")} if cleanup_out else None)
    out["flow_id"] = flow_id
    return out
