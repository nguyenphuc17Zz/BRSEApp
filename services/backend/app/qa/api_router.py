"""QA Phase 3 REST API: OpenAPI import, catalog, environments, API tests, suites, flows."""
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import encrypt_credential, mask_api_key
from app.intelligence.models import WorkItem
from app.qa.models import TestCase, TestStep
from app.qa.api_models import APIEndpoint, APIEnvironment, APITestConfig, APIAssertion, APITestFlow
from app.qa.execution_models import TestRun, TestExecution
from app.qa import schemas as S
from app.qa import engines as E1
from app.qa import execution_engines as X
from app.qa.router import _ts, ser_case
from app.qa.api_testing import openapi_parser as OP
from app.qa.api_testing import runner as RN
from app.qa.api_testing import scenario_engine as SC
from app.qa.api_testing import redact as R

router = APIRouter(prefix="/api/qa", tags=["QA API Testing"])


def _jloads(text: str, default):
    try:
        return json.loads(text or "") if (text or "").strip() else default
    except Exception:
        return default


def ser_endpoint(db_ep: APIEndpoint, req_code: Optional[str] = None,
                 tc_count: int = 0, last_result: Optional[str] = None,
                 last_build: Optional[str] = None) -> dict:
    return {"id": db_ep.id, "project_id": db_ep.project_id, "method": db_ep.method,
            "path": db_ep.path, "name": db_ep.name or "",
            "description": db_ep.description or "", "auth_type": db_ep.auth_type,
            "parameters": _jloads(db_ep.parameters_json, []),
            "request_body": _jloads(db_ep.request_body_json, {}),
            "responses": _jloads(db_ep.responses_json, {}),
            "tags": _jloads(db_ep.tags_json, []),
            "requirement_id": db_ep.requirement_id, "req_code": req_code,
            "spec_source": db_ep.spec_source, "spec_version": db_ep.spec_version,
            "test_case_count": tc_count, "last_result": last_result,
            "last_build": last_build,
            "created_at": _ts(db_ep.created_at), "updated_at": _ts(db_ep.updated_at)}


def ser_env(env: APIEnvironment) -> dict:
    secrets = _jloads(env.secrets_json, {})
    return {"id": env.id, "project_id": env.project_id, "name": env.name,
            "base_url": env.base_url or "",
            "variables": _jloads(env.variables_json, {}),
            "secret_keys": sorted(secrets.keys()),
            "secret_masked": {k: mask_api_key("x") if False else "***" for k in secrets.keys()},
            "is_default": env.is_default, "is_prod": RN.is_prod_env(env),
            "created_at": _ts(env.created_at), "updated_at": _ts(env.updated_at)}


def ser_config(cfg: APITestConfig, assertions: list) -> dict:
    return {"test_case_id": cfg.test_case_id, "endpoint_id": cfg.endpoint_id,
            "method": cfg.method, "url_template": cfg.url_template or "",
            "headers": _jloads(cfg.headers_json, {}),
            "query": _jloads(cfg.query_json, {}),
            "path_params": _jloads(cfg.path_params_json, {}),
            "body_text": cfg.body_text or "",
            "auth": _jloads(cfg.auth_ref_json, {}),
            "expected_status": cfg.expected_status, "timeout_s": cfg.timeout_s,
            "retry_network": cfg.retry_network, "spec_version": cfg.spec_version,
            "outdated_flag": cfg.outdated_flag, "is_setup": cfg.is_setup,
            "is_cleanup": cfg.is_cleanup,
            "extract_map": _jloads(cfg.extract_map_json, {}),
            "assertions": assertions}


def ser_assertion(a: APIAssertion) -> dict:
    return {"id": a.id, "test_case_id": a.test_case_id, "field": a.field,
            "target": a.target or "", "operator": a.operator,
            "expected_value": a.expected_value, "status": a.status,
            "ai_generated": a.ai_generated, "created_at": _ts(a.created_at)}


async def _api_test_ids(db: AsyncSession, project_id: Optional[str] = None):
    stmt = select(APITestConfig.test_case_id)
    if project_id:
        stmt = stmt.join(TestCase, TestCase.id == APITestConfig.test_case_id).where(
            TestCase.project_id == project_id)
    return set((await db.execute(stmt)).scalars().all())


# ---------- OpenAPI import (§28: deterministic, no AI) ----------
@router.post("/openapi:import")
async def import_openapi(payload: dict, db: AsyncSession = Depends(get_db)):
    project_id = payload.get("project_id")
    content = payload.get("content") or ""
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required.")
    try:
        spec, _fmt = OP.load_spec(content)
        parsed = OP.parse_openapi(spec)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    existing = (await db.execute(select(APIEndpoint).where(
        APIEndpoint.project_id == project_id))).scalars().all()
    old_sigs = [{"method": e.method, "path": e.path,
                 "parameters": _jloads(e.parameters_json, []),
                 "responses": _jloads(e.responses_json, {}),
                 "auth_type": e.auth_type} for e in existing]
    diff = OP.diff_spec(old_sigs, parsed)
    by_key = {(e.method, e.path): e for e in existing}
    imported = 0
    for ep in parsed["endpoints"]:
        row = by_key.get((ep["method"], ep["path"]))
        if row:
            row.name = ep["name"][:255]
            row.description = ep["description"]
            row.auth_type = ep["auth_type"]
            row.parameters_json = json.dumps(ep["parameters"], ensure_ascii=False)
            row.request_body_json = json.dumps(ep["request_body"], ensure_ascii=False)
            row.responses_json = json.dumps(ep["responses"], ensure_ascii=False)
            row.tags_json = json.dumps(ep["tags"], ensure_ascii=False)
            row.spec_source = "openapi"
            row.spec_version = parsed["version"][:50]
        else:
            db.add(APIEndpoint(
                project_id=project_id, method=ep["method"], path=ep["path"][:500],
                name=ep["name"][:255], description=ep["description"],
                auth_type=ep["auth_type"],
                parameters_json=json.dumps(ep["parameters"], ensure_ascii=False),
                request_body_json=json.dumps(ep["request_body"], ensure_ascii=False),
                responses_json=json.dumps(ep["responses"], ensure_ascii=False),
                tags_json=json.dumps(ep["tags"], ensure_ascii=False),
                spec_source="openapi", spec_version=parsed["version"][:50]))
            imported += 1
    await db.flush()
    # flag configs whose endpoint signature changed (§48)
    flagged = 0
    for key in diff["changed"]:
        method, path = key.split(" ", 1)
        ep_row = by_key.get((method, path))
        if not ep_row:
            continue
        cfgs = (await db.execute(select(APITestConfig).where(
            APITestConfig.endpoint_id == ep_row.id))).scalars().all()
        for c in cfgs:
            if not c.outdated_flag:
                c.outdated_flag = True
                flagged += 1
    await db.commit()
    return {"title": parsed["title"], "version": parsed["version"],
            "total": len(parsed["endpoints"]), "imported": imported,
            "updated": len(parsed["endpoints"]) - imported,
            "auth_schemes": parsed["auth_schemes"],
            "added": diff["added"], "changed": diff["changed"],
            "removed": diff["removed"], "flagged_outdated": flagged}


# ---------- Catalog ----------
@router.get("/endpoints", response_model=List[S.APIEndpointResponse])
async def list_endpoints(project_id: str, search: Optional[str] = None,
                         method: Optional[str] = None,
                         requirement_id: Optional[str] = None,
                         db: AsyncSession = Depends(get_db)):
    stmt = select(APIEndpoint).where(APIEndpoint.project_id == project_id).order_by(
        APIEndpoint.path, APIEndpoint.method)
    if method:
        stmt = stmt.where(APIEndpoint.method == method.upper())
    if requirement_id:
        stmt = stmt.where(APIEndpoint.requirement_id == requirement_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(APIEndpoint.path.like(like), APIEndpoint.name.like(like)))
    rows = (await db.execute(stmt.limit(300))).scalars().all()
    out = []
    for e in rows:
        tc_ids = (await db.execute(select(APITestConfig.test_case_id).where(
            APITestConfig.endpoint_id == e.id))).scalars().all()
        last_result = last_build = None
        req_code = None
        if e.requirement_id:
            req = await E1.get_requirement(db, e.requirement_id)
            req_code = getattr(req, "req_code", None) if req else None
        if tc_ids:
            last_ex = (await db.execute(select(TestExecution).where(
                TestExecution.test_case_id.in_(tc_ids)).order_by(desc(TestExecution.updated_at)).limit(1)
            )).scalars().first()
            if last_ex:
                last_result = last_ex.status
                run = (await db.execute(select(TestRun).where(
                    TestRun.id == last_ex.test_run_id))).scalars().first()
                last_build = run.version_build if run else None
        out.append(ser_endpoint(e, req_code, len(tc_ids), last_result, last_build))
    return out


@router.post("/endpoints", response_model=S.APIEndpointResponse)
async def create_endpoint(project_id: str, payload: S.APIEndpointCreate,
                          db: AsyncSession = Depends(get_db)):
    ep = APIEndpoint(
        project_id=project_id, method=payload.method.upper(), path=payload.path[:500],
        name=payload.name[:255], description=payload.description,
        auth_type=payload.auth_type,
        parameters_json=json.dumps(payload.parameters, ensure_ascii=False),
        request_body_json=json.dumps(payload.request_body, ensure_ascii=False),
        responses_json=json.dumps(payload.responses, ensure_ascii=False),
        tags_json=json.dumps(payload.tags, ensure_ascii=False),
        requirement_id=payload.requirement_id, spec_source=payload.spec_source)
    db.add(ep)
    await db.commit()
    await db.refresh(ep)
    return ser_endpoint(ep)


@router.patch("/endpoints/{endpoint_id}", response_model=S.APIEndpointResponse)
async def update_endpoint(endpoint_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    ep = (await db.execute(select(APIEndpoint).where(APIEndpoint.id == endpoint_id))).scalars().first()
    if not ep:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    for k in ("name", "description", "auth_type", "requirement_id"):
        if k in payload and payload[k] is not None:
            setattr(ep, k, payload[k])
    if payload.get("method"):
        ep.method = payload["method"].upper()
    if payload.get("path"):
        ep.path = payload["path"][:500]
    await db.commit()
    await db.refresh(ep)
    return ser_endpoint(ep)


@router.delete("/endpoints/{endpoint_id}")
async def delete_endpoint(endpoint_id: str, db: AsyncSession = Depends(get_db)):
    ep = (await db.execute(select(APIEndpoint).where(APIEndpoint.id == endpoint_id))).scalars().first()
    if not ep:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    await db.delete(ep)
    await db.commit()
    return {"status": "deleted", "id": endpoint_id}


# ---------- Environments (§8-10: secrets encrypted, masked, never in prompts) ----------
@router.get("/environments", response_model=List[S.APIEnvironmentResponse])
async def list_envs(project_id: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(APIEnvironment).where(
        APIEnvironment.project_id == project_id).order_by(APIEnvironment.name))).scalars().all()
    return [ser_env(e) for e in rows]


@router.post("/environments", response_model=S.APIEnvironmentResponse)
async def create_env(project_id: str, payload: S.APIEnvironmentCreate,
                     db: AsyncSession = Depends(get_db)):
    env = APIEnvironment(project_id=project_id, name=payload.name[:50],
                         base_url=(payload.base_url or "").rstrip("/"),
                         variables_json=json.dumps(payload.variables or {}, ensure_ascii=False),
                         is_default=payload.is_default)
    if payload.is_default:
        others = (await db.execute(select(APIEnvironment).where(
            APIEnvironment.project_id == project_id))).scalars().all()
        for o in others:
            o.is_default = False
    db.add(env)
    await db.commit()
    await db.refresh(env)
    return ser_env(env)


@router.patch("/environments/{env_id}", response_model=S.APIEnvironmentResponse)
async def update_env(env_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    env = (await db.execute(select(APIEnvironment).where(APIEnvironment.id == env_id))).scalars().first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    if payload.get("name"):
        env.name = payload["name"][:50]
    if "base_url" in payload and payload["base_url"] is not None:
        env.base_url = payload["base_url"].rstrip("/")
    if isinstance(payload.get("variables"), dict):
        env.variables_json = json.dumps(payload["variables"], ensure_ascii=False)
    if payload.get("is_default"):
        others = (await db.execute(select(APIEnvironment).where(
            APIEnvironment.project_id == env.project_id))).scalars().all()
        for o in others:
            o.is_default = (o.id == env.id)
    await db.commit()
    await db.refresh(env)
    return ser_env(env)


@router.post("/environments/{env_id}/secrets", response_model=S.APIEnvironmentResponse)
async def set_secret(env_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    """Write-only secret setter. Values are Fernet-encrypted; reads always masked."""
    env = (await db.execute(select(APIEnvironment).where(APIEnvironment.id == env_id))).scalars().first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    key = (payload.get("key") or "").strip()
    value = payload.get("value") or ""
    if not key or not value:
        raise HTTPException(status_code=400, detail="key and value are required.")
    secrets = _jloads(env.secrets_json, {})
    secrets[key] = encrypt_credential(value)
    env.secrets_json = json.dumps(secrets)
    await db.commit()
    await db.refresh(env)
    return ser_env(env)


@router.delete("/environments/{env_id}/secrets/{key}", response_model=S.APIEnvironmentResponse)
async def delete_secret(env_id: str, key: str, db: AsyncSession = Depends(get_db)):
    env = (await db.execute(select(APIEnvironment).where(APIEnvironment.id == env_id))).scalars().first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    secrets = _jloads(env.secrets_json, {})
    secrets.pop(key, None)
    env.secrets_json = json.dumps(secrets)
    await db.commit()
    await db.refresh(env)
    return ser_env(env)


@router.delete("/environments/{env_id}")
async def delete_env(env_id: str, db: AsyncSession = Depends(get_db)):
    env = (await db.execute(select(APIEnvironment).where(APIEnvironment.id == env_id))).scalars().first()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    await db.delete(env)
    await db.commit()
    return {"status": "deleted", "id": env_id}


# ---------- Scenario generation (§4-5) ----------
@router.post("/api-tests:generate")
async def generate_api_tests(payload: dict, db: AsyncSession = Depends(get_db)):
    endpoint_id = payload.get("endpoint_id")
    if not endpoint_id:
        raise HTTPException(status_code=400, detail="endpoint_id is required.")
    try:
        cases = await SC.generate_api_tests(
            db, endpoint_id, payload.get("requirement_id"),
            min(int(payload.get("max_cases") or 8), 12),
            payload.get("preferred_provider"), payload.get("model"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    out = []
    for tc in cases:
        await db.refresh(tc)
        cfg = (await db.execute(select(APITestConfig).where(
            APITestConfig.test_case_id == tc.id))).scalars().first()
        ass = (await db.execute(select(APIAssertion).where(
            APIAssertion.test_case_id == tc.id))).scalars().all()
        d = ser_case(tc)
        d["api_config"] = ser_config(cfg, [ser_assertion(a) for a in ass]) if cfg else None
        out.append(d)
    return out


# ---------- API test list/detail ----------
@router.get("/api-tests")
async def list_api_tests(project_id: str, requirement_id: Optional[str] = None,
                         method: Optional[str] = None, status: Optional[str] = None,
                         search: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    stmt = select(TestCase).join(APITestConfig, APITestConfig.test_case_id == TestCase.id).where(
        TestCase.project_id == project_id).order_by(desc(TestCase.created_at))
    if requirement_id:
        stmt = stmt.where(TestCase.requirement_id == requirement_id)
    if method:
        stmt = stmt.where(APITestConfig.method == method.upper())
    if status:
        stmt = stmt.where(TestCase.status == status.upper())
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(TestCase.title.like(like), TestCase.tc_code.like(like)))
    cases = (await db.execute(stmt.limit(300))).scalars().all()
    out = []
    for tc in cases:
        cfg = (await db.execute(select(APITestConfig).where(
            APITestConfig.test_case_id == tc.id))).scalars().first()
        ass = (await db.execute(select(APIAssertion).where(
            APIAssertion.test_case_id == tc.id))).scalars().all()
        last_ex = (await db.execute(select(TestExecution).where(
            TestExecution.test_case_id == tc.id).order_by(desc(TestExecution.updated_at)).limit(1)
        )).scalars().first()
        d = ser_case(tc)
        d["api_config"] = ser_config(cfg, [ser_assertion(a) for a in ass]) if cfg else None
        d["last_result"] = last_ex.status if last_ex else None
        out.append(d)
    return out


@router.get("/api-tests/{case_id}")
async def get_api_test(case_id: str, db: AsyncSession = Depends(get_db)):
    tc = (await db.execute(select(TestCase).where(TestCase.id == case_id))).scalars().first()
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    cfg = (await db.execute(select(APITestConfig).where(
        APITestConfig.test_case_id == case_id))).scalars().first()
    if not cfg:
        raise HTTPException(status_code=400, detail="Not an API test case.")
    ass = (await db.execute(select(APIAssertion).where(
        APIAssertion.test_case_id == case_id).order_by(APIAssertion.created_at))).scalars().all()
    req = await E1.get_requirement(db, tc.requirement_id) if tc.requirement_id else None
    hist = (await db.execute(select(TestExecution).where(
        TestExecution.test_case_id == case_id).order_by(desc(TestExecution.updated_at)).limit(20)
    )).scalars().all()
    hist_out = []
    for h in hist:
        run = (await db.execute(select(TestRun).where(TestRun.id == h.test_run_id))).scalars().first()
        hist_out.append({"status": h.status, "attempt_no": h.attempt_no,
                         "build": run.version_build if run else "",
                         "run_code": run.run_code if run else "",
                         "bug_id": h.bug_work_item_id,
                         "at": _ts(h.executed_at or h.created_at)})
    d = ser_case(tc)
    d["api_config"] = ser_config(cfg, [ser_assertion(a) for a in ass])
    d["requirement"] = {"id": req.id, "req_code": getattr(req, "req_code", None),
                        "title": req.title} if req else None
    d["history"] = hist_out
    return d


@router.patch("/api-tests/{case_id}/config")
async def update_api_config(case_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(select(APITestConfig).where(
        APITestConfig.test_case_id == case_id))).scalars().first()
    if not cfg:
        raise HTTPException(status_code=404, detail="API config not found")
    for k in ("method", "url_template", "body_text"):
        if k in payload and payload[k] is not None:
            setattr(cfg, k, payload[k] if k != "method" else payload[k].upper())
    for k, col in (("headers", "headers_json"), ("query", "query_json"),
                   ("path_params", "path_params_json"), ("auth", "auth_ref_json"),
                   ("extract_map", "extract_map_json")):
        if isinstance(payload.get(k), dict):
            setattr(cfg, col, json.dumps(payload[k], ensure_ascii=False))
    if "expected_status" in payload and payload["expected_status"] is not None:
        cfg.expected_status = int(payload["expected_status"])
    if "timeout_s" in payload and payload["timeout_s"] is not None:
        cfg.timeout_s = max(5, min(int(payload["timeout_s"]), 120))
    if "retry_network" in payload:
        cfg.retry_network = bool(payload["retry_network"])
    for k in ("is_setup", "is_cleanup"):
        if k in payload:
            setattr(cfg, k, bool(payload[k]))
    if payload.get("outdated_flag") is False:
        cfg.outdated_flag = False  # human reviewed after spec change
    await db.commit()
    ass = (await db.execute(select(APIAssertion).where(
        APIAssertion.test_case_id == case_id))).scalars().all()
    return ser_config(cfg, [ser_assertion(a) for a in ass])


# ---------- Assertions (§12-14) ----------
@router.post("/api-tests/{case_id}/assertions", response_model=S.APIAssertionResponse)
async def create_assertion(case_id: str, payload: S.APIAssertionCreate,
                           db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(select(APITestConfig).where(
        APITestConfig.test_case_id == case_id))).scalars().first()
    if not cfg:
        raise HTTPException(status_code=404, detail="API config not found")
    a = APIAssertion(test_case_id=case_id, field=payload.field[:20],
                     target=(payload.target or "")[:500],
                     operator=payload.operator[:20],
                     expected_value=payload.expected_value,
                     status="APPROVED", ai_generated=False)
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return ser_assertion(a)


@router.patch("/assertions/{assertion_id}", response_model=S.APIAssertionResponse)
async def update_assertion(assertion_id: str, payload: S.APIAssertionUpdate,
                           db: AsyncSession = Depends(get_db)):
    a = (await db.execute(select(APIAssertion).where(APIAssertion.id == assertion_id))).scalars().first()
    if not a:
        raise HTTPException(status_code=404, detail="Assertion not found")
    data = payload.model_dump(exclude_none=True)
    for k, v in data.items():
        if k == "status" and v.upper() not in ("DRAFT", "APPROVED", "REJECTED"):
            raise HTTPException(status_code=400, detail="Invalid status.")
        setattr(a, k, v.upper() if k == "status" else v)
    await db.commit()
    await db.refresh(a)
    return ser_assertion(a)


@router.delete("/assertions/{assertion_id}")
async def delete_assertion(assertion_id: str, db: AsyncSession = Depends(get_db)):
    a = (await db.execute(select(APIAssertion).where(APIAssertion.id == assertion_id))).scalars().first()
    if not a:
        raise HTTPException(status_code=404, detail="Assertion not found")
    await db.delete(a)
    await db.commit()
    return {"status": "deleted", "id": assertion_id}


@router.post("/api-tests/{case_id}/assertions:suggest")
async def suggest_assertions(case_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    rows = await SC.suggest_assertions(db, case_id, payload.get("sample_response"),
                                       payload.get("preferred_provider"), payload.get("model"))
    return [ser_assertion(r) for r in rows]


# ---------- Execution (§11, §15-18: sync, into Phase 2 TestExecution) ----------
@router.post("/api-tests/{case_id}/run")
async def run_one_api_test(case_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    environment_id = payload.get("environment_id")
    if not environment_id:
        raise HTTPException(status_code=400, detail="environment_id is required.")
    try:
        return await RN.execute_api_case(
            db, case_id, environment_id, payload.get("flow_vars") or {},
            payload.get("test_run_id"), None,
            payload.get("changed_by") or "user",
            payload.get("confirm_prod") or False)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api-suites:run")
async def run_api_suite(payload: dict, db: AsyncSession = Depends(get_db)):
    ids = payload.get("test_case_ids") or []
    environment_id = payload.get("environment_id")
    if not ids or not environment_id:
        raise HTTPException(status_code=400, detail="test_case_ids and environment_id are required.")
    try:
        return await RN.run_api_suite(
            db, ids, environment_id, payload.get("test_run_id"), None,
            payload.get("changed_by") or "user",
            payload.get("confirm_prod") or False,
            payload.get("flow_vars") or {})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/executions/{execution_id}/analyze-fail")
async def analyze_fail(execution_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    try:
        return await SC.analyze_failure(db, execution_id,
                                        payload.get("preferred_provider"), payload.get("model"))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/executions/{execution_id}/api-bug:draft")
async def draft_api_bug(execution_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    """Phase 2 bug draft + API block (endpoint/method/request/response/failed assertion), redacted."""
    from app.qa.execution_models import TestEvidence as _TE
    try:
        draft = await X.draft_bug_report(db, execution_id,
                                         payload.get("preferred_provider"), payload.get("model"))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    tc_id = draft.get("test_case_id")
    cfg = (await db.execute(select(APITestConfig).where(
        APITestConfig.test_case_id == tc_id))).scalars().first() if tc_id else None
    ev_rows = (await db.execute(select(_TE).where(_TE.execution_id == execution_id))).scalars().all()
    req_txt = next((e.text_content or "" for e in ev_rows if e.evidence_type == "api_request"), "")
    resp_txt = next((e.text_content or "" for e in ev_rows if e.evidence_type == "api_response"), "")
    try:
        req_doc = json.loads(req_txt or "{}")
    except Exception:
        req_doc = {"raw": (req_txt or "")[:1500]}
    try:
        resp_doc = json.loads(resp_txt or "{}")
    except Exception:
        resp_doc = {"raw": (resp_txt or "")[:1500]}
    failed = []
    try:
        actual_doc = json.loads(draft.get("actual_result") or "{}")
        failed = actual_doc.get("failed_assertions") or []
    except Exception:
        pass
    api_vi = (f"API: {cfg.method} {cfg.url_template} | "
              f"Status thực tế: {resp_doc.get('status_code', resp_doc.get('response', {}).get('status_code', '—'))}" if cfg else "")
    api_ja = ""
    if cfg:
        try:
            st = (resp_doc.get("response") or resp_doc).get("status_code", "—")
        except Exception:
            st = "—"
        api_ja = (f"【対象API】{cfg.method} {cfg.url_template}\n"
                  f"【期待結果】Status {cfg.expected_status}\n"
                  f"【実際結果】Status {st}\n"
                  f"【レスポンス】{(resp_txt or '')[:2000]}")
    draft["api_endpoint"] = f"{cfg.method} {cfg.url_template}" if cfg else ""
    draft["api_request"] = req_doc
    draft["api_response_excerpt"] = (resp_txt or "")[:3000]
    draft["failed_assertions"] = failed
    draft["summary_vi"] = (draft.get("summary_vi") or "") + (f"\n{api_vi}" if api_vi else "")
    draft["summary_ja"] = (draft.get("summary_ja") or "") + (f"\n{api_ja}" if api_ja else "")
    draft["notes_ja"] = draft.get("notes_ja") or ""
    return draft


# ---------- Flows (§25-26 minimal) ----------
@router.post("/flows")
async def create_flow(payload: dict, db: AsyncSession = Depends(get_db)):
    if not payload.get("project_id") or not payload.get("name"):
        raise HTTPException(status_code=400, detail="project_id and name are required.")
    flow = APITestFlow(
        project_id=payload["project_id"], name=payload["name"][:255],
        description=payload.get("description") or "",
        step_case_ids_json=json.dumps(payload.get("step_case_ids") or [], ensure_ascii=False),
        setup_case_id=payload.get("setup_case_id"),
        cleanup_case_id=payload.get("cleanup_case_id"))
    db.add(flow)
    await db.commit()
    await db.refresh(flow)
    return {"id": flow.id, "project_id": flow.project_id, "name": flow.name,
            "description": flow.description,
            "step_case_ids": _jloads(flow.step_case_ids_json, []),
            "setup_case_id": flow.setup_case_id, "cleanup_case_id": flow.cleanup_case_id}


@router.get("/flows")
async def list_flows(project_id: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(APITestFlow).where(
        APITestFlow.project_id == project_id).order_by(desc(APITestFlow.created_at)))).scalars().all()
    return [{"id": f.id, "project_id": f.project_id, "name": f.name,
             "description": f.description,
             "step_case_ids": _jloads(f.step_case_ids_json, []),
             "setup_case_id": f.setup_case_id, "cleanup_case_id": f.cleanup_case_id}
            for f in rows]


@router.post("/flows/{flow_id}/run")
async def run_flow(flow_id: str, payload: dict, db: AsyncSession = Depends(get_db)):
    if not payload.get("environment_id"):
        raise HTTPException(status_code=400, detail="environment_id is required.")
    try:
        return await RN.run_api_flow(
            db, flow_id, payload["environment_id"], payload.get("test_run_id"), None,
            payload.get("changed_by") or "user", payload.get("confirm_prod") or False)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------- API coverage (§29-30) ----------
@router.get("/coverage/api")
async def api_coverage(project_id: str, db: AsyncSession = Depends(get_db)):
    endpoints = (await db.execute(select(APIEndpoint).where(
        APIEndpoint.project_id == project_id).order_by(APIEndpoint.path))).scalars().all()
    out = []
    for e in endpoints:
        tc_ids = (await db.execute(select(APITestConfig.test_case_id).where(
            APITestConfig.endpoint_id == e.id))).scalars().all()
        last_result = last_build = None
        happy_only = True
        auth_tested = e.auth_type == "none"
        if tc_ids:
            cases = (await db.execute(select(TestCase).where(
                TestCase.id.in_(tc_ids)))).scalars().all()
            cats = {(c.case_type or "") for c in cases}
            happy_only = cats <= {"Happy", "Validation"}
            if e.auth_type != "none":
                auth_tested = any("uth" in (c.case_type or "") or "ermission" in (c.case_type or "")
                                  for c in cases)
            last_ex = (await db.execute(select(TestExecution).where(
                TestExecution.test_case_id.in_(tc_ids)).order_by(desc(TestExecution.updated_at)).limit(1)
            )).scalars().first()
            if last_ex:
                last_result = last_ex.status
                run = (await db.execute(select(TestRun).where(
                    TestRun.id == last_ex.test_run_id))).scalars().first()
                last_build = run.version_build if run else None
        gaps = []
        if not tc_ids:
            gaps.append("No Test")
        if happy_only and tc_ids:
            gaps.append("Only happy path")
        if not auth_tested:
            gaps.append("Missing unauthorized test")
        # response codes in spec never asserted?
        spec_codes = set()
        try:
            for k in (_jloads(e.responses_json, {}) or {}).keys():
                spec_codes.add(str(k))
        except Exception:
            pass
        if spec_codes and tc_ids:
            asserted = set()
            for cid in tc_ids:
                rows = (await db.execute(select(APIAssertion).where(
                    APIAssertion.test_case_id == cid, APIAssertion.field == "status",
                    APIAssertion.status == "APPROVED"))).scalars().all()
                asserted.update(str(r.expected_value) for r in rows)
            missing_codes = sorted(spec_codes - asserted - {"default"})
            if missing_codes:
                gaps.append(f"Untested status codes: {','.join(missing_codes)}")
        out.append({"id": e.id, "method": e.method, "path": e.path, "name": e.name,
                    "test_case_count": len(tc_ids), "last_result": last_result,
                    "last_build": last_build, "gaps": gaps})
    return out


# ---------- Test data preview (§23) ----------
@router.get("/test-data:preview")
async def preview_test_data(kind: str = "email"):
    from app.qa.api_testing.variables import dynamic_value
    ok, val = dynamic_value(kind)
    if not ok:
        raise HTTPException(status_code=400, detail="Unknown kind (email|username|uuid|timestamp|random).")
    return {"kind": kind, "value": val}
