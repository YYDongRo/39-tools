from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from agent_devtools.action import ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.integrations.playwright import RecordedPlaywrightExecutor


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "trace" / "executor-fill-failure"
TARGET_SELECTOR = "#readonly-input"


def main() -> None:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    trace_dir = TRACE_ROOT / run_id
    page_url = Path(__file__).with_name(
        "browser_diagnostics.html"
    ).resolve().as_uri()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 650})
        page.goto(page_url)

        with RecordedPlaywrightExecutor(page, trace_dir) as executor:
            action = executor.fill(
                TARGET_SELECTOR,
                "Agent debugging",
                timeout_ms=500,
            )

        browser.close()

    if (
        action.status is not ActionStatus.FAILURE
        or action.failure_category is not FailureCategory.TARGET_NOT_EDITABLE
    ):
        raise RuntimeError("the non-editable diagnosis was not recorded")

    print(f"Failure category: {action.failure_category.value}")
    print(f"Report: {executor.report_path.resolve()}")


if __name__ == "__main__":
    main()
