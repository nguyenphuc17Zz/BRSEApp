"""Phase 3 pure-logic tests: OpenAPI parser, assertions, variables, redaction."""
import json
import pytest
from app.qa.api_testing import openapi_parser as OP
from app.qa.api_testing.assertion_engine import evaluate, evaluate_all, get_path
from app.qa.api_testing.variables import substitute, build_variable_scope
from app.qa.api_testing import redact as R

SAMPLE_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "User API", "version": "1.2.0"},
    "paths": {
        "/api/users": {
            "post": {
                "summary": "Create user",
                "tags": ["users"],
                "security": [{"bearerAuth": []}],
                "requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}},
                "responses": {"201": {"description": "created"}, "400": {"description": "bad"}, "401": {"description": "unauth"}},
            }
        },
        "/api/users/{id}": {
            "get": {
                "operationId": "getUser",
                "parameters": [{"name": "id", "in": "path", "required": True}],
                "responses": {"200": {"description": "ok"}, "404": {"description": "nf"}},
            }
        },
    },
    "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
}


def test_openapi_json_and_yaml_parse():
    parsed = OP.parse_openapi(SAMPLE_SPEC)
    assert parsed["version"] == "1.2.0"
    assert len(parsed["endpoints"]) == 2
    post = next(e for e in parsed["endpoints"] if e["method"] == "POST")
    assert post["auth_type"] == "bearer"
    assert set(post["responses"].keys()) == {"201", "400", "401"}
    get = next(e for e in parsed["endpoints"] if e["method"] == "GET")
    assert get["auth_type"] == "none"

    as_json, fmt = OP.load_spec(json.dumps(SAMPLE_SPEC))
    assert fmt == "json" and as_json["openapi"] == "3.0.0"
    with pytest.raises(ValueError):
        OP.load_spec("{not json")


def test_openapi_yaml_parse():
    yaml_text = """
openapi: 3.0.0
info: {title: T, version: '2.0'}
paths:
  /api/login:
    post:
      summary: Login
      responses: {'200': {description: ok}}
"""
    doc, fmt = OP.load_spec(yaml_text)
    assert fmt == "yaml"
    parsed = OP.parse_openapi(doc)
    assert len(parsed["endpoints"]) == 1


def test_diff_spec_flags_changes():
    old = [{"method": "POST", "path": "/api/users", "parameters": [],
            "responses": {"201": {}, "400": {}}, "auth_type": "bearer"}]
    new_parsed = OP.parse_openapi(SAMPLE_SPEC)
    diff = OP.diff_spec(old, new_parsed)
    assert "POST /api/users" in diff["changed"]  # 401 added
    assert "GET /api/users/{id}" in diff["added"]


def test_assertion_evaluation():
    resp = {"status_code": 201, "headers": {"Content-Type": "application/json", "X-Req": "1"},
            "body": {"data": {"id": 7, "status": "ACTIVE", "tags": []}}, "latency_ms": 120}
    assert evaluate({"field": "status", "operator": "eq", "expected_value": "201"}, resp)["passed"]
    assert evaluate({"field": "json", "target": "data.id", "operator": "exists"}, resp)["passed"]
    assert evaluate({"field": "json", "target": "data.status", "operator": "eq",
                     "expected_value": "ACTIVE"}, resp)["passed"]
    assert not evaluate({"field": "json", "target": "data.status", "operator": "eq",
                         "expected_value": "LOCKED"}, resp)["passed"]
    assert evaluate({"field": "json", "target": "data.id", "operator": "type",
                     "expected_value": "integer"}, resp)["passed"]
    assert not evaluate({"field": "json", "target": "data.missing", "operator": "exists"}, resp)["passed"]
    assert evaluate({"field": "header", "target": "X-Req", "operator": "exists"}, resp)["passed"]
    assert evaluate({"field": "time", "operator": "lt", "expected_value": "5000"}, resp)["passed"]
    assert evaluate({"field": "json", "target": "data.tags", "operator": "empty"}, resp)["passed"]
    out = evaluate_all([
        {"field": "status", "operator": "eq", "expected_value": "201"},
        {"field": "json", "target": "data.status", "operator": "eq", "expected_value": "LOCKED"},
    ], resp)
    assert out["passed"] == 1 and out["failed"] == 1 and not out["all_passed"]


def test_get_path_nested_and_list():
    assert get_path({"a": {"b": [{"c": 1}]}}, "a.b.0.c") == (True, 1)
    assert get_path({"a": 1}, "a.b") == (False, None)


def test_variable_substitution_and_dynamic():
    scope = build_variable_scope({"BASE_URL": "https://stg"}, {"AUTH_TOKEN": "s3cr3t"}, {"user_id": 42})
    url, missing = substitute("{{BASE_URL}}/api/users/{{user_id}}", scope)
    assert url == "https://stg/api/users/42" and missing == []
    tok, _ = substitute("Bearer {{AUTH_TOKEN}}", scope)
    assert tok == "Bearer s3cr3t"
    obj, missing2 = substitute({"a": "{{NOPE}}", "b": [1, "{{BASE_URL}}"]}, scope)
    assert obj["b"][1] == "https://stg" and missing2 == ["NOPE"]
    email, _ = substitute("{{TEST_EMAIL}}", {})
    assert "@example.com" in email


def test_redaction_kills_secrets():
    headers = {"Authorization": "Bearer abc123", "Content-Type": "application/json",
               "X-Api-Key": "key-999"}
    assert R.redact_headers(headers) == {"Authorization": "***REDACTED***",
                                         "Content-Type": "application/json",
                                         "X-Api-Key": "***REDACTED***"}
    body = {"email": "a@b.com", "password": "hunter2", "nested": {"token": "t"}}
    red = R.redact_json(body)
    assert red["password"] == "***REDACTED***" and red["nested"]["token"] == "***REDACTED***"
    assert red["email"] == "a@b.com"
    req = R.redact_request("POST", "https://x/api", headers, {}, body)
    assert req["headers"]["Authorization"] == "***REDACTED***"
    assert "hunter2" not in json.dumps(req)
