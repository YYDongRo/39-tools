from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from agent_devtools.action import ActionOutcome, ActionStatus
from agent_devtools.integrations.playwright import (
    PlaywrightAction,
    TextExpectation,
    expect_text,
    run_playwright_agent,
)
from agent_devtools.serialization import read_session_json
from agent_devtools.session_recorder import SessionRecorder


if TYPE_CHECKING:
    from playwright.sync_api import Page


playwright = pytest.importorskip(
    "playwright.sync_api",
    reason="the agent trajectory test requires the browser extra",
)

SEARCH_QUERY = "Agent debugging"
EXPECTED_PLAYER_STATUS = "Playing: Agent debugging"
TARGET_URL = (
    Path(__file__).parents[2] / "examples" / "video_search_agent.html"
).resolve().as_uri()


def decide_next_action(page: Page) -> PlaywrightAction | None:
    if page.url != TARGET_URL:
        return PlaywrightAction("navigate", {"url": TARGET_URL})

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


def test_records_complete_agent_trajectory(tmp_path: Path) -> None:
    trace_dir = tmp_path / "trajectory"

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 700})

        task_verification = expect_text(
            page,
            TextExpectation(
                selector="#player-status",
                expected="Playing: Agent debugging",
            ),
        )
        with SessionRecorder(
            trace_dir,
            lambda path: page.screenshot(path=str(path), full_page=True),
            goal="Search for 'Agent debugging' and play the result",
            task_verification=task_verification,
        ) as recorder:
            recorded_actions = run_playwright_agent(
                page,
                recorder,
                decide_next_action,
            )
        session = recorder.session

        browser.close()

    assert session.action_count == 5
    assert recorded_actions == session.actions
    assert [action.action_type for action in session.actions] == [
        "navigate",
        "fill",
        "click",
        "click",
        "click",
    ]
    assert session.actions[0].arguments == {"url": TARGET_URL}
    assert all(
        action.status is ActionStatus.SUCCESS for action in session.actions
    )
    assert all(action.verification is None for action in session.actions)
    assert session.verification is not None
    assert session.verification.passed
    assert session.outcome is ActionOutcome.SUCCESS
    assert read_session_json(trace_dir / "session.json") == session
    assert (trace_dir / "report.html").is_file()

    for action_number in range(1, 6):
        action_dir = trace_dir / "actions" / f"{action_number:03d}"
        assert (action_dir / "before.png").stat().st_size > 0
        assert (action_dir / "after.png").stat().st_size > 0

    report = (trace_dir / "report.html").read_text(encoding="utf-8")
    assert "Playing: Agent debugging" in report
    assert "Search for &#x27;Agent debugging&#x27; and play the result" in report
    assert "Task verification" in report
    assert "task successful" in report
    assert "5 actions" in report


def test_agent_skips_steps_already_completed_in_page_state(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "partial-trajectory"

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(TARGET_URL)
        page.locator("#search").fill(SEARCH_QUERY)
        page.locator("#search-button").click()

        with SessionRecorder(
            trace_dir,
            lambda path: page.screenshot(path=str(path), full_page=True),
            goal="Play the existing search result",
            task_verification=expect_text(
                page,
                TextExpectation(
                    selector="#player-status",
                    expected=EXPECTED_PLAYER_STATUS,
                ),
            ),
        ) as recorder:
            recorded_actions = run_playwright_agent(
                page,
                recorder,
                decide_next_action,
            )

        browser.close()

    assert [action.arguments["selector"] for action in recorded_actions] == [
        "#video-result",
        "#play",
    ]
    assert recorder.session.action_count == 2
    assert recorder.session.outcome is ActionOutcome.SUCCESS
