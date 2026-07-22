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
TASK_GOAL = f"Search for {SEARCH_QUERY!r} and play the result"


def run_agent_trajectory(page: Page, trace_dir: Path) -> ActionSession:
    def capture_screenshot(path: Path) -> None:
        page.screenshot(path=str(path), full_page=True)

    actions: list[tuple[str, dict[str, object]]] = [
        ("fill", {"selector": "#search", "text": SEARCH_QUERY}),
        ("click", {"selector": "#search-button"}),
        ("click", {"selector": "#video-result"}),
        ("click", {"selector": "#play"}),
    ]
    recorder = SessionRecorder(
        trace_dir,
        capture_screenshot,
        goal=TASK_GOAL,
    )
    for action_type, arguments in actions:
        action = record_playwright_action(
            page,
            recorder,
            action_type,
            arguments,
        )
        if action.status is ActionStatus.FAILURE:
            break

    recorder.verify_task(
        expect_text(
            page,
            TextExpectation(
                selector="#player-status",
                expected="Playing: Agent debugging",
            ),
        )
    )

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

    if (
        session.action_count != 4
        or session.outcome is not ActionOutcome.SUCCESS
    ):
        raise RuntimeError("the agent did not complete the video playback task")

    print(f"Recorded actions: {session.action_count}")
    print(f"Final task outcome: {session.outcome.value}")
    print(f"Report: {(trace_dir / 'report.html').resolve()}")


if __name__ == "__main__":
    main()
