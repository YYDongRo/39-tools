from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from agent_devtools.action import ActionOutcome, ActionStatus
from agent_devtools.integrations.playwright import (
    TextExpectation,
    expect_text,
    record_playwright_action,
)
from agent_devtools.session import ActionSession
from agent_devtools.session_recorder import SessionRecorder


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "trace" / "video-search-agent"
SEARCH_QUERY = "Agent debugging"


def run_agent_trajectory(page: Page, trace_dir: Path) -> ActionSession:
    def capture_screenshot(path: Path) -> None:
        page.screenshot(path=str(path), full_page=True)

    recorder = SessionRecorder(trace_dir, capture_screenshot)
    actions: list[tuple[str, dict[str, object]]] = [
        ("fill", {"selector": "#search", "text": SEARCH_QUERY}),
        ("click", {"selector": "#search-button"}),
        ("click", {"selector": "#video-result"}),
        ("click", {"selector": "#play"}),
    ]

    for action_type, arguments in actions:
        verification = None
        if arguments.get("selector") == "#play":
            verification = expect_text(
                page,
                TextExpectation(
                    selector="#player-status",
                    expected="Playing: Agent debugging",
                ),
            )

        action = record_playwright_action(
            page,
            recorder,
            action_type,
            arguments,
            verification=verification,
        )
        if action.status is ActionStatus.FAILURE:
            break

    return recorder.session


def main() -> None:
    page_path = Path(__file__).with_suffix(".html").resolve()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    trace_dir = TRACE_ROOT / run_id

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 700})
        page.goto(page_path.as_uri())
        session = run_agent_trajectory(page, trace_dir)
        browser.close()

    final_action = session.actions[-1]
    if (
        session.action_count != 4
        or final_action.outcome is not ActionOutcome.SUCCESS
    ):
        raise RuntimeError("the agent did not complete the video playback task")

    print(f"Recorded actions: {session.action_count}")
    print(f"Final outcome: {final_action.outcome.value}")
    print(f"Report: {(trace_dir / 'report.html').resolve()}")


if __name__ == "__main__":
    main()
