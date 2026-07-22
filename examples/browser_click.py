from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from agent_devtools.action import ActionOutcome
from agent_devtools.integrations.playwright import (
    TextExpectation,
    expect_text,
    record_playwright_click_trace,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "trace" / "browser-click"


def main() -> None:
    page_path = Path(__file__).with_suffix(".html").resolve()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    trace_dir = TRACE_ROOT / run_id

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 650})
        page.goto(page_path.as_uri())

        action = record_playwright_click_trace(
            page,
            "#agent-action",
            trace_dir,
            verification=expect_text(
                page,
                TextExpectation(
                    selector="#status",
                    expected="The browser click succeeded.",
                    timeout_ms=2_000,
                ),
            ),
        )
        browser.close()

    if action.outcome is not ActionOutcome.SUCCESS:
        raise RuntimeError("the browser action did not reach the expected state")

    print(f"Verified browser action trace written to {trace_dir}")


if __name__ == "__main__":
    main()
