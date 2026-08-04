from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from agent_devtools.action import ActionStatus
from agent_devtools.recorder import record_action
from agent_devtools.replay import replay_fill
from agent_devtools.report import write_action_html
from agent_devtools.serialization import read_action_json, write_action_json


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

    with sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)

        source_page = browser.new_page()
        source_page.goto(page_path.as_uri())
        source_action = record_action(
            action_type="fill",
            arguments={
                "selector": SELECTOR,
                "text": TEXT,
                "timeout_ms": TIMEOUT_MS,
            },
            operation=lambda: source_page.locator(SELECTOR).fill(
                TEXT,
                timeout=TIMEOUT_MS,
            ),
        )
        source_page.close()
        if source_action.status is not ActionStatus.SUCCESS:
            raise RuntimeError("the source browser fill did not succeed")

        original_path = trace_dir / "original.json"
        write_action_json(source_action, original_path)
        write_action_html(source_action, trace_dir / "original.html")
        loaded_action = read_action_json(original_path)

        replay_page = browser.new_page(viewport={"width": 1000, "height": 650})
        replay_page.goto(page_path.as_uri())
        replay_page.screenshot(
            path=str(trace_dir / "before.png"),
            full_page=True,
        )

        def execute_fill(
            selector: str,
            text: str,
            timeout_ms: int | None,
        ) -> None:
            locator = replay_page.locator(selector)
            if timeout_ms is None:
                locator.fill(text)
            else:
                locator.fill(text, timeout=timeout_ms)

        result = replay_fill(
            loaded_action,
            execute_fill,
            screenshot_before=Path("before.png"),
            screenshot_after=Path("after.png"),
        )
        replay_page.screenshot(
            path=str(trace_dir / "after.png"),
            full_page=True,
        )
        input_value = replay_page.locator(SELECTOR).input_value()
        browser.close()

    write_action_json(result.replayed_action, trace_dir / "replay.json")
    write_action_html(result.replayed_action, trace_dir / "report.html")

    if not result.outcome_matches or input_value != TEXT:
        raise RuntimeError("the browser fill replay did not reproduce the input")

    print(f"Original action: {trace_dir / 'original.json'}")
    print(f"Replay action: {trace_dir / 'replay.json'}")
    print(f"Report: {trace_dir / 'report.html'}")


if __name__ == "__main__":
    main()
