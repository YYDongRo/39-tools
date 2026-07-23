from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from agent_devtools.action import ActionOutcome
from agent_devtools.integrations.playwright import (
    PlaywrightAction,
    TextExpectation,
    VisibilityExpectation,
    expect_text,
    run_playwright_agent,
)
from agent_devtools.session import ActionSession
from agent_devtools.session_recorder import SessionRecorder


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "trace" / "video-search-agent"
SEARCH_QUERY = "Agent debugging"
TASK_GOAL = f"Search for {SEARCH_QUERY!r} and play the result"
EXPECTED_PLAYER_STATUS = "Playing: Agent debugging"
TARGET_URL = Path(__file__).with_suffix(".html").resolve().as_uri()


def decide_next_action(page: Page) -> PlaywrightAction | None:
    if page.url != TARGET_URL:
        return PlaywrightAction(
            "navigate",
            {"url": TARGET_URL},
            expectation=VisibilityExpectation("#search"),
        )

    if page.locator("#search").input_value() != SEARCH_QUERY:
        return PlaywrightAction(
            "fill",
            {"selector": "#search", "text": SEARCH_QUERY},
        )

    expected_result = f"Result for: {SEARCH_QUERY}"
    result = page.locator("#video-result")
    if (
        not page.locator("#results").is_visible()
        or result.inner_text() != expected_result
    ):
        return PlaywrightAction("click", {"selector": "#search-button"})

    if not page.locator("#player").is_visible():
        return PlaywrightAction("click", {"selector": "#video-result"})

    if page.locator("#player-status").inner_text() != EXPECTED_PLAYER_STATUS:
        return PlaywrightAction("click", {"selector": "#play"})

    return None


def run_agent_trajectory(page: Page, trace_dir: Path) -> ActionSession:
    def capture_screenshot(path: Path) -> None:
        page.screenshot(path=str(path), full_page=True)

    task_verification = expect_text(
        page,
        TextExpectation(
            selector="#player-status",
            expected=EXPECTED_PLAYER_STATUS,
        ),
    )

    with SessionRecorder(
        trace_dir,
        capture_screenshot,
        goal=TASK_GOAL,
        task_verification=task_verification,
    ) as recorder:
        run_playwright_agent(page, recorder, decide_next_action)

    return recorder.session


def main() -> None:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    trace_dir = TRACE_ROOT / run_id

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 700})
        session = run_agent_trajectory(page, trace_dir)
        browser.close()

    if (
        session.action_count != 5
        or session.outcome is not ActionOutcome.SUCCESS
    ):
        raise RuntimeError("the agent did not complete the video playback task")

    print(f"Recorded actions: {session.action_count}")
    print(f"Final task outcome: {session.outcome.value}")
    print(f"Report: {(trace_dir / 'report.html').resolve()}")


if __name__ == "__main__":
    main()
