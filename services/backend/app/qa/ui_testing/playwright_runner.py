"""Background Playwright runner (Chromium-first). Interprets flow_json directly.

AI-generated Python is display-only; execution never exec()s model output.
Progress is polled via get_ui_status(). Server restart orphans are recovered
to BLOCKED on next status poll.
"""
import asyncio
import datetime
import json
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DATA_DIR
from app.core.logging import logger
from app.core.security import decrypt_credential
from app.qa.models import TestCase
from app.qa.api_models import APIEnvironment
from app.qa.ui_models import UIAutomationScript, UIElementMapping
from app.qa.execution_models import TestRun, TestExecution, TestEvidence
from app.qa import execution_engines as X
from app.qa.api_testing import variables as V
from app.qa.api_testing import redact as R

EVIDENCE_DIR = Path(DATA_DIR) / "qa-evidence"
BROWSER_DIR = Path(DATA_DIR) / "qa-browser"
STEP_TIMEOUT_MS = 30_000
MAX_CONSOLE_ITEMS = 50

# execution_id -> {"progress": {...}, "cancel": bool}
UI_JOBS: Dict[str, Dict[str, Any]] = {}


def _loads(text: str, default: Any) -> Any:
    try:
        return json.loads(text or "") if (text or "").strip() else default
    except Exception:
        return default


def _same_origin(url: str, base: str) -> bool:
    try:
        u, b = urlparse(url), urlparse(base)
        return (u.scheme, u.hostname, u.port) == (b.scheme, b.hostname, b.port)
    except Exception:
        return False


async def _load_script(db: AsyncSession, test_case_id: str) -> UIAutomationScript:
    script = (await db.execute(select(UIAutomationScript).where(
        UIAutomationScript.test_case_id == test_case_id))).scalars().first()
    if not script:
        raise ValueError("No automation script for this test case (NOT_GENERATED).")
    return script


def _build_locator(page, target: Dict[str, Any]):
    s = (target.get("strategy") or "text").lower()
    v = target.get("value", "")
    o = target.get("options") or {}
    if s == "role":
        return page.get_by_role(v, name=o.get("name")) if o.get("name") else page.get_by_role(v)
    if s == "label":
        return page.get_by_label(v, exact=o.get("exact", False))
    if s == "placeholder":
        return page.get_by_placeholder(v, exact=o.get("exact", False))
    if s == "text":
        return page.get_by_text(v, exact=o.get("exact", False))
    if s == "testid":
        return page.get_by_test_id(v)
    return page.locator(v)


async def start_ui_run(
    db: AsyncSession, test_case_id: str, environment_id: str,
    test_run_id: Optional[str] = None, flow_vars: Optional[Dict[str, Any]] = None,
    changed_by: str = "user", confirm_prod: bool = False,
    browser: str = "chromium", force: bool = False,
) -> Dict[str, Any]:
    tc = (await db.execute(select(TestCase).where(TestCase.id == test_case_id))).scalars().first()
    if not tc:
        raise ValueError("Test case not found")
    script = await _load_script(db, test_case_id)
    if script.status == "DISABLED":
        raise ValueError("Automation is DISABLED for this test case.")
    if script.status != "APPROVED" and not force:
        raise ValueError(f"Script status is {script.status} — review and approve before running.")
    if script.manual_preferred and not force:
        raise ValueError("Flagged Manual Preferred — confirm explicitly (force) to run automation.")
    env = (await db.execute(select(APIEnvironment).where(
        APIEnvironment.id == environment_id))).scalars().first()
    if not env:
        raise ValueError("Environment not found")
    if tc.project_id != env.project_id:
        raise ValueError("Environment belongs to another project.")
    from app.qa.api_testing.runner import is_prod_env
    if is_prod_env(env) and not confirm_prod:
        raise ValueError("ProductionGuard: UI run on PROD needs explicit confirmation.")
    if browser.lower() != "chromium":
        raise ValueError("Phase 4 supports Chromium only.")

    run_id = test_run_id
    if not run_id:
        run_id = (await X.create_run(db, tc.project_id, {
            "name": f"Ad-hoc UI {datetime.datetime.utcnow().strftime('%Y/%m/%d %H:%M')}",
            "environment": env.name, "tester": changed_by,
            "scope": {"adhoc": True, "type": "WEB_UI"}})).id
    ex = TestExecution(test_run_id=run_id, test_case_id=tc.id,
                       requirement_id=tc.requirement_id,
                       acceptance_criterion_id=tc.acceptance_criterion_id,
                       attempt_no=1, status="RUNNING", tester=changed_by,
                       case_snapshot_json=json.dumps(
                           {"tc_code": tc.tc_code, "title": tc.title,
                            "expected_result": tc.expected_result,
                            "script_version": script.script_version}, ensure_ascii=False))
    db.add(ex)
    await db.flush()
    await X.log_history(db, ex.id, "status", "NOT_RUN", "RUNNING", changed_by)
    run = (await db.execute(select(TestRun).where(TestRun.id == run_id))).scalars().first()
    if run and run.status in ("READY", "DRAFT"):
        run.status = "IN_PROGRESS"
        await db.flush()
    await db.commit()

    UI_JOBS[ex.id] = {"progress": {"current_step": 0, "total_steps": 0,
                                   "label": "queued", "browser": "chromium",
                                   "environment": env.name, "started_at": datetime.datetime.utcnow().isoformat()},
                      "cancel": False}
    task = asyncio.create_task(_run_flow_job(
        ex.id, tc.project_id, env.id, dict(flow_vars or {}), changed_by))
    UI_JOBS[ex.id]["task"] = task
    task.add_done_callback(lambda t: _job_done(ex.id, t))
    return {"execution_id": ex.id, "test_run_id": run_id, "status": "RUNNING"}


def _job_done(execution_id: str, task: "asyncio.Task") -> None:
    if task.cancelled():
        job = UI_JOBS.get(execution_id)
        if job:
            job["progress"]["label"] = "cancelled"
    elif task.exception():
        logger.warning(f"UI job {execution_id} crashed: {task.exception()}")


async def cancel_ui_run(execution_id: str) -> Dict[str, Any]:
    job = UI_JOBS.get(execution_id)
    if not job:
        raise ValueError("No live UI job for this execution.")
    job["cancel"] = True
    task = job.get("task")
    if task and not task.done():
        task.cancel()
    return {"execution_id": execution_id, "cancelled": True}


async def get_ui_status(db: AsyncSession, execution_id: str) -> Dict[str, Any]:
    ex = (await db.execute(select(TestExecution).where(
        TestExecution.id == execution_id))).scalars().first()
    if not ex:
        raise ValueError("Execution not found")
    job = UI_JOBS.get(execution_id)
    if ex.status == "RUNNING" and not job:
        # orphan (e.g. server restart): recover deterministically
        old = ex.status
        ex.status = "BLOCKED"
        ex.fail_reason = "Interrupted (server restart during automation)."
        ex.executed_at = datetime.datetime.utcnow()
        await db.flush()
        await X.log_history(db, ex.id, "status", old, "BLOCKED", "system")
        await X.refresh_exec_coverage(db, ex.requirement_id)
        await db.commit()
        return {"execution_id": ex.id, "status": "BLOCKED",
                "progress": {"label": "recovered: interrupted"},
                "fail_reason": ex.fail_reason}
    progress = dict(job["progress"]) if job else {"label": "finished"}
    return {"execution_id": ex.id, "status": ex.status,
            "progress": progress, "fail_reason": ex.fail_reason,
            "actual_result": ex.actual_result}


async def _run_flow_job(execution_id: str, project_id: str, environment_id: str,
                        flow_vars: Dict[str, Any], changed_by: str) -> None:
    from app.core.database import async_session_maker
    from playwright.async_api import async_playwright

    async with async_session_maker() as db:
        ex = (await db.execute(select(TestExecution).where(
            TestExecution.id == execution_id))).scalars().first()
        if not ex:
            return
        tc = (await db.execute(select(TestCase).where(TestCase.id == ex.test_case_id))).scalars().first()
        script = await _load_script(db, ex.test_case_id)
        env = (await db.execute(select(APIEnvironment).where(
            APIEnvironment.id == environment_id))).scalars().first()
        flow = _loads(script.flow_json, [])
        job = UI_JOBS.get(execution_id, {})
        progress = job.get("progress", {})
        progress["total_steps"] = len(flow)

        secrets = {k: decrypt_credential(v)
                   for k, v in _loads(env.secrets_json, {}).items()}
        scope = V.build_variable_scope(_loads(env.variables_json, {}), secrets, flow_vars or {})
        base_url = str(scope.get("WEB_BASE_URL") or env.base_url or "").rstrip("/")
        if not base_url:
            await _finish(db, ex, tc, "BLOCKED", "Invalid Test Configuration: no base URL.",
                          {}, progress, changed_by)
            return

        console_errors: List[Dict[str, Any]] = []
        failed_requests: List[Dict[str, Any]] = []
        screenshots: List[str] = []
        trace_path: Optional[str] = None
        run_dir = EVIDENCE_DIR / ex.test_run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        started = datetime.datetime.utcnow()
        failed_step: Optional[Dict[str, Any]] = None
        failed_assertion = ""
        error_class = ""
        final_url = ""
        passed_steps = 0

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                ctx_dir = BROWSER_DIR / project_id / env.name
                ctx_dir.mkdir(parents=True, exist_ok=True)
                context = await browser.new_context(
                    viewport={"width": 1366, "height": 768},
                    storage_state=str(ctx_dir / "storage.json") if (ctx_dir / "storage.json").exists() else None)
                await context.tracing.start(screenshots=True, snapshots=True)
                page = await context.new_page()
                page.on("console", lambda msg: console_errors.append(
                    {"type": msg.type, "text": msg.text[:500]})
                    if msg.type == "error" and len(console_errors) < MAX_CONSOLE_ITEMS else None)
                page.on("response", lambda r: failed_requests.append(
                    {"url": r.url[:500], "status": r.status})
                    if (r.status >= 400 and len(failed_requests) < MAX_CONSOLE_ITEMS) else None)

                async def _shot(name: str) -> str:
                    path = run_dir / f"{ex.id[:8]}_{name}.png"
                    await page.screenshot(path=str(path))
                    screenshots.append(path.relative_to(Path(DATA_DIR)).as_posix())
                    return screenshots[-1]

                try:
                    await asyncio.wait_for(_execute_steps(
                        db, page, base_url, flow, scope, progress, ex.id,
                        _shot, lambda: bool(UI_JOBS.get(execution_id, {}).get("cancel"))),
                        timeout=script.timeout_s or 180)
                    passed_steps = len(flow)
                    final_url = page.url
                    await _shot("final")
                except asyncio.CancelledError:
                    raise
                except Exception as step_err:
                    failed_step = dict(progress.get("failed_step") or {})
                    failed_assertion = progress.get("failed_assertion", "") or ""
                    error_class = progress.get("error_class", "") or type(step_err).__name__
                    try:
                        final_url = page.url
                    except Exception:
                        pass
                    try:
                        await _shot("fail")
                    except Exception:
                        pass
                    try:
                        trace_path = str(run_dir / f"{ex.id[:8]}_trace.zip")
                        await context.tracing.stop(path=trace_path)
                        trace_path = Path(trace_path).relative_to(Path(DATA_DIR)).as_posix()
                    except Exception as te:
                        logger.warning(f"trace save failed: {te}")
                        trace_path = None
                else:
                    try:
                        await context.tracing.stop()
                    except Exception:
                        pass
                try:
                    await context.storage_state(path=str(ctx_dir / "storage.json"))
                except Exception as se:
                    logger.warning(f"session persist failed: {se}")
                await browser.close()
        except asyncio.CancelledError:
            await _finish(db, ex, tc, "BLOCKED", "Cancelled by user.",
                          {"cancelled": True}, progress, changed_by)
            return
        except Exception as e:
            logger.warning(f"UI job {execution_id} fatal: {e}\n{traceback.format_exc()}")
            await _finish(db, ex, tc, "FAIL", f"Runner error: {e}",
                          {"fatal": str(e)[:500]}, progress, changed_by)
            return

        duration_ms = int((datetime.datetime.utcnow() - started).total_seconds() * 1000)
        if failed_step:
            await _finish(db, ex, tc, "FAIL",
                          f"{failed_step.get('label', 'step')} — {failed_assertion or error_class}",
                          {"failed_step": failed_step, "failed_assertion": failed_assertion,
                           "current_url": final_url, "duration_ms": duration_ms,
                           "browser": "chromium", "error_class": error_class,
                           "console_errors": console_errors[:MAX_CONSOLE_ITEMS],
                           "failed_requests": failed_requests[:MAX_CONSOLE_ITEMS],
                           "screenshots": screenshots, "trace": trace_path,
                           "steps_passed": passed_steps, "steps_total": len(flow)},
                          progress, changed_by,
                          extra_evidence={"console_errors": console_errors,
                                          "failed_requests": failed_requests,
                                          "screenshots": screenshots, "trace": trace_path})
        else:
            await _finish(db, ex, tc, "PASS",
                          f"All {len(flow)} step(s) passed in {duration_ms}ms.",
                          {"current_url": final_url, "duration_ms": duration_ms,
                           "browser": "chromium", "screenshots": screenshots,
                           "console_errors": console_errors[:10],
                           "steps_passed": passed_steps, "steps_total": len(flow)},
                          progress, changed_by,
                          extra_evidence={"screenshots": screenshots})


async def _execute_steps(db: AsyncSession, page, base_url: str, flow: List[Dict[str, Any]],
                         scope: Dict[str, Any], progress: Dict[str, Any],
                         execution_id: str, shot, is_cancelled) -> None:
    from playwright.async_api import expect as _expect
    for i, step in enumerate(flow or [], 1):
        if is_cancelled():
            raise asyncio.CancelledError()
        action = (step.get("action") or "").lower()
        progress["current_step"] = i
        progress["label"] = step.get("label") or action
        try:
            if action in ("open", "navigate", "goto"):
                url, missing = V.substitute(step.get("value") or "", scope)
                url = str(url)
                if url.startswith("/"):
                    url = base_url + url
                if not _same_origin(url, base_url):
                    raise ValueError(f"Blocked navigation outside configured environment: {url}")
                if missing:
                    raise ValueError(f"Unresolved variables {missing}")
                await page.goto(url, wait_until="domcontentloaded", timeout=STEP_TIMEOUT_MS)
            elif action in ("fill", "click", "select", "check", "press", "upload"):
                target = await _resolve_target(db, step)
                value, missing = V.substitute(step.get("value", ""), scope)
                if missing and action == "fill":
                    raise ValueError(f"Unresolved variables {missing}")
                loc = _build_locator(page, target)
                if action == "fill":
                    await loc.fill(str(value), timeout=STEP_TIMEOUT_MS)
                elif action == "click":
                    await loc.click(timeout=STEP_TIMEOUT_MS)
                elif action == "select":
                    await loc.select_option(str(value), timeout=STEP_TIMEOUT_MS)
                elif action == "check":
                    await loc.check(timeout=STEP_TIMEOUT_MS)
                elif action == "press":
                    await loc.press(str(value or "Enter"), timeout=STEP_TIMEOUT_MS)
                elif action == "upload":
                    await loc.set_input_files(str(value), timeout=STEP_TIMEOUT_MS)
            elif action.startswith("verify_") or action == "assert":
                target = await _resolve_target(db, step, allow_empty=True)
                value, _ = V.substitute(step.get("value", ""), scope)
                loc = _build_locator(page, target) if target else page
                await _verify(page, loc, action, value, step.get("assertion") or "")
                if step.get("checkpoint"):
                    await shot(f"step{i:02d}")
            else:
                raise ValueError(f"Unsupported action: {action}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            progress["failed_step"] = {"order": i, "label": step.get("label") or action,
                                       "action": action}
            progress["failed_assertion"] = str(e)[:500]
            progress["error_class"] = _classify_step_error(e)
            raise


async def _resolve_target(db: AsyncSession, step: Dict[str, Any],
                          allow_empty: bool = False) -> Dict[str, Any]:
    if step.get("selector_required"):
        raise ValueError(f"Selector Required: {step.get('element_hint') or step.get('label')}")
    mid = step.get("mapping_id")
    if mid:
        m = (await db.execute(select(UIElementMapping).where(
            UIElementMapping.id == mid))).scalars().first()
        if not m:
            raise ValueError(f"Element mapping not found: {mid} (UI Changed?)")
        if m.status != "ACTIVE":
            raise ValueError(f"Mapping '{m.element_name}' needs review — approve before running.")
        try:
            return json.loads(m.locator_json or "{}")
        except Exception:
            raise ValueError(f"Mapping '{m.element_name}' has invalid locator JSON.")
    target = step.get("target") or {}
    if target.get("strategy"):
        return target
    if allow_empty:
        return {}
    raise ValueError(f"Step '{step.get('label')}' has no locator and is not flagged Selector Required.")


async def _verify(page, loc, action: str, value: Any, assertion: str):
    from playwright.async_api import expect as _expect
    a = (assertion or action).lower()
    if "hidden" in a or action == "verify_hidden":
        await _expect(loc).to_be_hidden(timeout=STEP_TIMEOUT_MS)
    elif "url" in a or action in ("verify_url", "wait_url"):
        import re as _re
        await _expect(page).to_have_url(_re.compile(str(value)), timeout=STEP_TIMEOUT_MS)
    elif "enabled" in a:
        await _expect(loc).to_be_enabled(timeout=STEP_TIMEOUT_MS)
    elif "disabled" in a:
        await _expect(loc).to_be_disabled(timeout=STEP_TIMEOUT_MS)
    elif "value" in a or action == "verify_value":
        await _expect(loc).to_have_value(str(value), timeout=STEP_TIMEOUT_MS)
    elif "count" in a or action == "verify_count":
        await _expect(loc).to_have_count(int(value) if str(value).isdigit() else 1,
                                         timeout=STEP_TIMEOUT_MS)
    elif value:
        await _expect(loc).to_contain_text(str(value), timeout=STEP_TIMEOUT_MS)
    else:
        await _expect(loc).to_be_visible(timeout=STEP_TIMEOUT_MS)


def _classify_step_error(e: Exception) -> str:
    name = type(e).__name__
    msg = str(e).lower()
    if "timeout" in name.lower() or "timeout" in msg:
        return "Timeout"
    if "selector required" in msg or "needs review" in msg or "not found" in msg and "mapping" in msg:
        return "Possible Selector Issue"
    if "unresolved variables" in msg or "unsupported action" in msg or "invalid test configuration" in msg:
        return "Possible Test Configuration Issue"
    if "blocked navigation" in msg or "productionguard" in msg:
        return "Possible Environment Issue"
    if "expect" in name.lower() or "assertion" in msg:
        return "Possible Application Bug"
    return "Unknown"


async def _finish(db: AsyncSession, ex: TestExecution, tc: TestCase, status: str,
                  fail_reason: Optional[str], actual_doc: Dict[str, Any],
                  progress: Dict[str, Any], changed_by: str,
                  extra_evidence: Optional[Dict[str, Any]] = None) -> None:
    old = ex.status
    ex.status = status
    ex.actual_result = json.dumps(actual_doc, ensure_ascii=False, default=str)[:6000]
    ex.fail_reason = fail_reason
    ex.executed_at = datetime.datetime.utcnow()
    await db.flush()
    await X.log_history(db, ex.id, "status", old, status, changed_by)
    extra_evidence = extra_evidence or {}
    for shot_rel in (extra_evidence.get("screenshots") or []):
        db.add(TestEvidence(execution_id=ex.id, test_case_id=ex.test_case_id,
                            requirement_id=ex.requirement_id,
                            evidence_type="screenshot", title="Screenshot",
                            file_path=shot_rel, mime_type="image/png",
                            created_by=changed_by))
    if extra_evidence.get("trace"):
        db.add(TestEvidence(execution_id=ex.id, test_case_id=ex.test_case_id,
                            requirement_id=ex.requirement_id,
                            evidence_type="file", title="Playwright trace (trace.zip)",
                            file_path=extra_evidence["trace"],
                            mime_type="application/zip", created_by=changed_by))
    tech = {k: v for k, v in extra_evidence.items() if k in ("console_errors", "failed_requests")}
    if tech and (tech.get("console_errors") or tech.get("failed_requests")):
        db.add(TestEvidence(execution_id=ex.id, test_case_id=ex.test_case_id,
                            requirement_id=ex.requirement_id,
                            evidence_type="console_error",
                            title="Console errors / failed network",
                            text_content=json.dumps(R.redact_json(tech), ensure_ascii=False)[:8000],
                            created_by=changed_by))
    await db.flush()
    await X.refresh_exec_coverage(db, ex.requirement_id)
    await db.commit()
    progress["label"] = f"finished: {status}"
