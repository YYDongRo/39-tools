from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from agent_devtools.integrations.playwright import (
    diagnose_playwright_click_failure,
    record_playwright_click,
)
from agent_devtools.replay import replay_click
from agent_devtools.report import write_action_html
from agent_devtools.serialization import read_action_json, write_action_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "trace" / "browser-replay"


def main() -> None:
    page_path = Path(__file__).with_name("browser_click.html").resolve()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    trace_dir = TRACE_ROOT / run_id
    before_path = trace_dir / "before.png"
    after_path = trace_dir / "after.png"
    trace_dir.mkdir(parents=True)

    with sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        source_page = browser.new_page()
        source_page.goto(page_path.as_uri())
        source_action = record_playwright_click(
            source_page,
            "#missing",
            timeout_ms=500,
        )
        source_page.close()
        write_action_json(source_action, trace_dir / "original.json")
        loaded_action = read_action_json(trace_dir / "original.json")

        replay_page = browser.new_page(viewport={"width": 1000, "height": 650})
        replay_page.goto(page_path.as_uri())
        replay_page.screenshot(path=str(before_path), full_page=True)

        def execute_click(selector: str, timeout_ms: int | None) -> None:
            if timeout_ms is None:
                replay_page.locator(selector).click()
            else:
                replay_page.locator(selector).click(timeout=timeout_ms)

        result = replay_click(
            loaded_action,
            execute_click,
            screenshot_before=Path("before.png"),
            screenshot_after=Path("after.png"),
            diagnose_failure=lambda action: diagnose_playwright_click_failure(
                replay_page,
                action,
            ),
        )

        replay_page.screenshot(path=str(after_path), full_page=True)
        browser.close()

    write_action_json(result.replayed_action, trace_dir / "replay.json")
    write_action_html(result.replayed_action, trace_dir / "report.html")

    if not result.outcome_matches:
        raise RuntimeError("the replay outcome did not match the original action")

    print(f"Browser replay trace written to {trace_dir}")


if __name__ == "__main__":
    main()
