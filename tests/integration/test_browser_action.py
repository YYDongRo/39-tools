from pathlib import Path

import pytest

from agent_devtools.action import ActionOutcome, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.integrations.playwright import (
    TextExpectation,
    expect_text,
    record_playwright_click,
)
from agent_devtools.recorder import record_action
from agent_devtools.report import write_action_html
from agent_devtools.serialization import read_action_json, write_action_json


playwright = pytest.importorskip(
    "playwright.sync_api",
    reason="the browser integration test requires the browser extra",
)


def test_records_real_browser_click(tmp_path: Path) -> None:
    page_path = (
        Path(__file__).parents[2] / "examples" / "browser_click.html"
    ).resolve()
    before_path = tmp_path / "before.png"
    after_path = tmp_path / "after.png"
    trace_path = tmp_path / "action.json"
    report_path = tmp_path / "report.html"

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 650})
        page.goto(page_path.as_uri())
        page.screenshot(path=str(before_path), full_page=True)

        action = record_playwright_click(
            page,
            "#agent-action",
            screenshot_before=Path("before.png"),
            screenshot_after=Path("after.png"),
            verification=expect_text(
                page,
                TextExpectation(
                    selector="#status",
                    expected="The browser click succeeded.",
                ),
            ),
        )

        page.screenshot(path=str(after_path), full_page=True)
        browser.close()

    write_action_json(action, trace_path)
    write_action_html(action, report_path)

    assert action.action_type == "click"
    assert action.arguments == {"selector": "#agent-action"}
    assert action.status is ActionStatus.SUCCESS
    assert action.duration_ms >= 0
    assert action.verification.passed
    assert action.verification.failure_reason is None
    assert action.outcome is ActionOutcome.SUCCESS
    assert before_path.stat().st_size > 0
    assert after_path.stat().st_size > 0
    assert before_path.read_bytes() != after_path.read_bytes()
    assert read_action_json(trace_path) == action
    report = report_path.read_text(encoding="utf-8")
    assert 'class="status status-success"' in report
    assert "<dt>Verification status</dt><dd>passed</dd>" in report
    assert "The browser click succeeded." in report


def test_structured_text_expectation_reports_mismatch() -> None:
    page_path = (
        Path(__file__).parents[2] / "examples" / "browser_click.html"
    ).resolve()

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(page_path.as_uri())

        action = record_playwright_click(
            page,
            "#agent-action",
            verification=expect_text(
                page,
                TextExpectation(
                    selector="#status",
                    expected="The task was saved.",
                    timeout_ms=100,
                ),
            ),
        )

        browser.close()

    assert action.status is ActionStatus.SUCCESS
    assert action.verification is not None
    assert not action.verification.passed
    assert action.verification.observed_state == "The browser click succeeded."
    assert action.verification.evidence == {
        "expectation_type": "text_equals",
        "selector": "#status",
        "selector_count": 1,
        "timeout_ms": 100,
    }
    assert action.failure_reason is None
    assert action.outcome is ActionOutcome.FAILURE


def test_structured_text_expectation_rejects_ambiguous_selector() -> None:
    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<p class="status">Saved</p><p class="status">Saved</p>'
        )

        verification = expect_text(
            page,
            TextExpectation(
                selector=".status",
                expected="Saved",
                timeout_ms=100,
            ),
        )()

        browser.close()

    assert not verification.passed
    assert verification.observed_state == "Saved"
    assert verification.evidence["selector_count"] == 2
    assert verification.failure_reason == (
        "expected selector '.status' to match exactly one element, observed 2"
    )
    assert verification.failure_category is FailureCategory.VERIFICATION_MISMATCH


def test_classifies_real_browser_timeout() -> None:
    page_path = (
        Path(__file__).parents[2] / "examples" / "browser_click.html"
    ).resolve()

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(page_path.as_uri())

        action = record_action(
            action_type="click",
            arguments={"selector": "#missing", "timeout_ms": 100},
            operation=lambda: page.locator("#missing").click(timeout=100),
        )

        browser.close()

    assert action.status is ActionStatus.FAILURE
    assert action.failure_category is FailureCategory.TIMEOUT
    assert action.failure_reason is not None
    assert action.failure_reason.startswith("TimeoutError:")
