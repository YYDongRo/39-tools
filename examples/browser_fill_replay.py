from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from agent_devtools.action import ActionStatus
from agent_devtools.integrations.playwright import (
    RecordedPlaywrightExecutor,
    replay_playwright_session_action,
)
from agent_devtools.serialization import read_session_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "trace" / "browser-fill-replay"
SELECTOR = "#visible-input"
TEXT = "Agent debugging"
TIMEOUT_MS = 500


def main() -> None:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    trace_dir = TRACE_ROOT / run_id
    trace_dir.mkdir(parents=True)
    page_path = (
        Path(__file__).with_name("browser_diagnostics.html").resolve()
    )
    task = "Open the diagnostics page and fill the visible input."
    source_dir = trace_dir / "original"
    replay_dir = trace_dir / "replay"

    with sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)

        source_page = browser.new_page()
        with RecordedPlaywrightExecutor(
            source_page,
            source_dir,
            goal=task,
        ) as executor:
            executor.navigate(page_path.as_uri())
            source_action = executor.fill(
                SELECTOR,
                TEXT,
                timeout_ms=TIMEOUT_MS,
            )
        source_page.close()
        if source_action.status is not ActionStatus.SUCCESS:
            raise RuntimeError("the source browser fill did not succeed")

        source_session = read_session_json(source_dir / "session.json")

        replay_page = browser.new_page(
            viewport={"width": 1000, "height": 650}
        )
        result = replay_playwright_session_action(
            replay_page,
            source_session,
            target_action_number=2,
            output_dir=replay_dir,
        )
        input_value = replay_page.locator(SELECTOR).input_value()
        browser.close()

    if not result.reproduced or input_value != TEXT:
        raise RuntimeError("the browser context replay did not reproduce the input")

    print(f"Original report: {source_dir / 'report.html'}")
    print(f"Replay report: {result.report_path}")


if __name__ == "__main__":
    main()
