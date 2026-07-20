from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from agent_devtools.action import ActionStatus
from agent_devtools.session_recorder import SessionRecorder


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "trace" / "browser-session"


def main() -> None:
    page_path = Path(__file__).with_suffix(".html").resolve()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    trace_dir = TRACE_ROOT / run_id

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 700})
        page.goto(page_path.as_uri())

        def capture_screenshot(path: Path) -> None:
            page.screenshot(path=str(path), full_page=True)

        recorder = SessionRecorder(trace_dir, capture_screenshot)
        recorder.record(
            action_type="click",
            arguments={"selector": "#open-panel"},
            operation=lambda: page.locator("#open-panel").click(),
        )
        recorder.record(
            action_type="fill",
            arguments={"selector": "#task-name", "text": "Debug agent run"},
            operation=lambda: page.locator("#task-name").fill("Debug agent run"),
        )
        recorder.record(
            action_type="click",
            arguments={"selector": "#missing-confirm-action", "timeout_ms": 500},
            operation=lambda: page.locator("#missing-confirm-action").click(
                timeout=500
            ),
        )
        browser.close()

    expected_statuses = [
        ActionStatus.SUCCESS,
        ActionStatus.SUCCESS,
        ActionStatus.FAILURE,
    ]
    if [action.status for action in recorder.session.actions] != expected_statuses:
        raise RuntimeError("the browser session did not produce the expected statuses")

    print(f"Browser session trace written to {trace_dir}")


if __name__ == "__main__":
    main()
