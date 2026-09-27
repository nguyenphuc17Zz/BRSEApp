"""Locator policy: priority order, validation, and Python code rendering.

Priority (§5): role > label > placeholder > text > testid > stable CSS.
Forbidden: nth-child, absolute XPath, fragile/position-based selectors, hard waits.
"""
import re
from typing import Any, Dict, List, Tuple

STRATEGY_ORDER = ["role", "label", "placeholder", "text", "testid", "css"]

FORBIDDEN_PATTERNS = [
    (re.compile(r"nth-child", re.IGNORECASE), "nth-child is fragile"),
    (re.compile(r"^\s*/(html|/)"), "absolute XPath is forbidden"),
    (re.compile(r"xpath\s*=", re.IGNORECASE), "XPath locators are forbidden"),
    (re.compile(r"waitForTimeout\s*\(\s*\d{3,}", re.IGNORECASE), "hard wait is forbidden"),
    (re.compile(r"time\.sleep\s*\(\s*\d", re.IGNORECASE), "hard sleep is forbidden"),
]


def validate_locator(strategy: str, value: str) -> List[str]:
    """Returns list of policy violations (empty = compliant)."""
    violations = []
    s = (strategy or "").lower()
    v = value or ""
    if s not in STRATEGY_ORDER:
        violations.append(f"Unknown strategy '{strategy}'. Use one of {STRATEGY_ORDER}.")
    for pattern, msg in FORBIDDEN_PATTERNS:
        if pattern.search(v):
            violations.append(f"{msg}: {v[:120]}")
    if s == "css" and (" > " in v and v.count(">") >= 3):
        violations.append(f"Deep CSS chain is fragile: {v[:120]}")
    return violations


def locator_expression(strategy: str, value: str, options: Dict[str, Any] = None) -> str:
    """Renders a Python Playwright locator expression, e.g. page.get_by_role(...)."""
    s = (strategy or "").lower()
    opts = options or {}
    q = lambda x: repr(x)
    if s == "role":
        extra = ""
        if opts.get("name") is not None:
            extra += f", name={q(opts['name'])}"
        if opts.get("exact"):
            extra += ", exact=True"
        return f"page.get_by_role({q(value)}{extra})"
    if s == "label":
        extra = ", exact=True" if opts.get("exact") else ""
        return f"page.get_by_label({q(value)}{extra})"
    if s == "placeholder":
        extra = ", exact=True" if opts.get("exact") else ""
        return f"page.get_by_placeholder({q(value)}{extra})"
    if s == "text":
        extra = ", exact=True" if opts.get("exact") else ""
        return f"page.get_by_text({q(value)}{extra})"
    if s == "testid":
        return f"page.get_by_test_id({q(value)})"
    # stable css
    return f"page.locator({q(value)})"


def render_flow_as_python(flow: List[Dict[str, Any]], base_url: str = "") -> str:
    """Deterministically renders flow_json into readable Playwright Python (display only).

    The runner interprets flow_json directly; this code is for the Advanced tab.
    Auto-wait style: expect() assertions, no hard sleeps.
    """
    lines = [
        "import re",
        "from playwright.async_api import async_playwright, expect",
        "",
        "async def run():",
        "    async with async_playwright() as p:",
        "        browser = await p.chromium.launch()",
        "        page = await browser.new_page()",
    ]
    if base_url:
        lines.append(f"        BASE_URL = {base_url!r}")
    for i, step in enumerate(flow or [], 1):
        action = (step.get("action") or "").lower()
        target = step.get("target") or {}
        value = step.get("value", "")
        assertion = step.get("assertion") or ""
        loc = locator_expression(target.get("strategy", "text"),
                                 target.get("value", step.get("target_name", "?")),
                                 target.get("options"))
        lines.append(f"        # Step {i}: {step.get('label') or action} {value!r}".rstrip())
        if action in ("open", "navigate", "goto"):
            lines.append(f"        await page.goto({value!r})")
        elif action == "fill":
            lines.append(f"        await {loc}.fill({value!r})")
        elif action == "click":
            lines.append(f"        await {loc}.click()")
        elif action == "select":
            lines.append(f"        await {loc}.select_option({value!r})")
        elif action == "check":
            lines.append(f"        await {loc}.check()")
        elif action == "press":
            lines.append(f"        await {loc}.press({value!r})")
        elif action == "upload":
            lines.append(f"        await {loc}.set_input_files({value!r})")
        elif action.startswith("verify_") or assertion:
            lines.append(_render_assertion(action, loc, value, assertion))
        else:
            lines.append(f"        await {loc}.click()  # {action}")
    lines += ["        await browser.close()", ""]
    return "\n".join(lines)


def _render_assertion(action: str, loc: str, value: Any, assertion: str) -> str:
    a = (assertion or action).lower()
    if "hidden" in a or action == "verify_hidden":
        return f"        await expect({loc}).to_be_hidden()"
    if "url" in a or action in ("verify_url", "wait_url"):
        return f"        await expect(page).to_have_url(re.compile({str(value)!r}))"
    if "enabled" in a:
        return f"        await expect({loc}).to_be_enabled()"
    if "disabled" in a:
        return f"        await expect({loc}).to_be_disabled()"
    if "value" in a or action == "verify_value":
        return f"        await expect({loc}).to_have_value({str(value)!r})"
    if "count" in a or action == "verify_count":
        return f"        await expect({loc}).to_have_count({int(value) if str(value).isdigit() else 1})"
    # default: visible text
    if value:
        return f"        await expect({loc}).to_contain_text({str(value)!r})"
    return f"        await expect({loc}).to_be_visible()"


def validate_flow(flow: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """Validates a whole flow against policy. Returns (ok, violations)."""
    problems = []
    for i, step in enumerate(flow or [], 1):
        action = (step.get("action") or "").lower()
        if action in ("sleep", "wait", "waitfortimeout"):
            problems.append(f"Step {i}: hard wait forbidden, use expect/wait-for-state.")
            continue
        target = step.get("target") or {}
        if step.get("selector_required"):
            continue  # explicitly flagged, not a violation
        if not target.get("strategy") and action not in ("open", "navigate", "goto"):
            problems.append(f"Step {i}: missing locator and not flagged Selector Required.")
            continue
        if target.get("strategy"):
            for v in validate_locator(target.get("strategy"), target.get("value", "")):
                problems.append(f"Step {i}: {v}")
    return (len(problems) == 0, problems)
