from pathlib import Path

import pytest

from agent_devtools.action import ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.integrations.playwright import (
    RecordedPlaywrightExecutor,
    record_playwright_click,
)
from agent_devtools.serialization import read_session_json


playwright = pytest.importorskip(
    "playwright.sync_api",
    reason="the Playwright diagnostics test requires the browser extra",
)


@pytest.mark.parametrize(
    ("selector", "category", "expected_evidence"),
    [
        (
            "#missing-target",
            FailureCategory.TARGET_NOT_FOUND,
            {
                "selector": "#missing-target",
                "selector_count": 0,
                "target_visible": None,
                "target_enabled": None,
            },
        ),
        (
            "#hidden-target",
            FailureCategory.TARGET_NOT_VISIBLE,
            {
                "selector": "#hidden-target",
                "selector_count": 1,
                "target_visible": False,
                "target_enabled": True,
            },
        ),
        (
            ".ambiguous-target",
            FailureCategory.TARGET_AMBIGUOUS,
            {
                "selector": ".ambiguous-target",
                "selector_count": 2,
                "target_visible": None,
                "target_enabled": None,
            },
        ),
        (
            "#disabled-target",
            FailureCategory.TARGET_DISABLED,
            {
                "selector": "#disabled-target",
                "selector_count": 1,
                "target_visible": True,
                "target_enabled": False,
            },
        ),
    ],
)
def test_diagnoses_failed_browser_click(
    selector: str,
    category: FailureCategory,
    expected_evidence: dict[str, object],
) -> None:
    page_path = (
        Path(__file__).parents[2] / "examples" / "browser_diagnostics.html"
    ).resolve()

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(page_path.as_uri())

        action = record_playwright_click(page, selector, timeout_ms=100)

        browser.close()

    assert action.status is ActionStatus.FAILURE
    assert action.failure_category is category
    assert action.failure_evidence == expected_evidence


def test_successful_browser_click_has_no_failure_evidence() -> None:
    page_path = (
        Path(__file__).parents[2] / "examples" / "browser_diagnostics.html"
    ).resolve()

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(page_path.as_uri())

        action = record_playwright_click(page, "#visible-target", timeout_ms=2_000)

        browser.close()

    assert action.status is ActionStatus.SUCCESS
    assert action.failure_category is None
    assert action.failure_evidence == {}


@pytest.mark.parametrize(
    ("selector", "category"),
    [
        ("#missing-target", FailureCategory.TARGET_NOT_FOUND),
        (".ambiguous-target", FailureCategory.TARGET_AMBIGUOUS),
        ("#hidden-target", FailureCategory.TARGET_NOT_VISIBLE),
        ("#disabled-target", FailureCategory.TARGET_DISABLED),
    ],
)
def test_executor_persists_click_failure_diagnosis(
    tmp_path: Path,
    selector: str,
    category: FailureCategory,
) -> None:
    page_path = (
        Path(__file__).parents[2] / "examples" / "browser_diagnostics.html"
    ).resolve()
    trace_dir = tmp_path / category.value

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(page_path.as_uri())

        with RecordedPlaywrightExecutor(page, trace_dir) as executor:
            action = executor.click(selector, timeout_ms=100)

        browser.close()

    loaded_action = read_session_json(
        trace_dir / "session.json"
    ).actions[0]
    report = (trace_dir / "report.html").read_text(encoding="utf-8")

    assert action.status is ActionStatus.FAILURE
    assert action.failure_category is category
    assert loaded_action == action
    assert category.value in report
