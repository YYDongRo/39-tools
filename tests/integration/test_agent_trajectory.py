from pathlib import Path

import pytest

from agent_devtools.action import ActionOutcome, ActionStatus
from agent_devtools.integrations.playwright import (
    TextExpectation,
    expect_text,
    record_playwright_action,
)
from agent_devtools.serialization import read_session_json
from agent_devtools.session_recorder import SessionRecorder


playwright = pytest.importorskip(
    "playwright.sync_api",
    reason="the agent trajectory test requires the browser extra",
)


def test_records_complete_agent_trajectory(tmp_path: Path) -> None:
    page_path = (
        Path(__file__).parents[2] / "examples" / "video_search_agent.html"
    ).resolve()
    trace_dir = tmp_path / "trajectory"

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 700})
        page.goto(page_path.as_uri())

        recorder = SessionRecorder(
            trace_dir,
            lambda path: page.screenshot(path=str(path), full_page=True),
            goal="Search for 'Agent debugging' and play the result",
        )
        record_playwright_action(
            page,
            recorder,
            "fill",
            {"selector": "#search", "text": "Agent debugging"},
        )
        record_playwright_action(
            page,
            recorder,
            "click",
            {"selector": "#search-button"},
        )
        record_playwright_action(
            page,
            recorder,
            "click",
            {"selector": "#video-result"},
        )
        record_playwright_action(
            page,
            recorder,
            "click",
            {"selector": "#play"},
        )
        recorder.verify_task(
            expect_text(
                page,
                TextExpectation(
                    selector="#player-status",
                    expected="Playing: Agent debugging",
                ),
            ),
        )
        session = recorder.session

        browser.close()

    assert session.action_count == 4
    assert [action.action_type for action in session.actions] == [
        "fill",
        "click",
        "click",
        "click",
    ]
    assert all(
        action.status is ActionStatus.SUCCESS for action in session.actions
    )
    assert all(action.verification is None for action in session.actions)
    assert session.verification is not None
    assert session.verification.passed
    assert session.outcome is ActionOutcome.SUCCESS
    assert read_session_json(trace_dir / "session.json") == session
    assert (trace_dir / "report.html").is_file()

    for action_number in range(1, 5):
        action_dir = trace_dir / "actions" / f"{action_number:03d}"
        assert (action_dir / "before.png").stat().st_size > 0
        assert (action_dir / "after.png").stat().st_size > 0

    report = (trace_dir / "report.html").read_text(encoding="utf-8")
    assert "Playing: Agent debugging" in report
    assert "Search for &#x27;Agent debugging&#x27; and play the result" in report
    assert "Task verification" in report
    assert "task successful" in report
    assert "4 actions" in report
