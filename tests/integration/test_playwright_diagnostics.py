from pathlib import Path

import pytest

from agent_devtools.action import ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.integrations.playwright import record_playwright_click


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

        action = record_playwright_click(page, "#visible-target", timeout_ms=100)

        browser.close()

    assert action.status is ActionStatus.SUCCESS
    assert action.failure_category is None
    assert action.failure_evidence == {}
