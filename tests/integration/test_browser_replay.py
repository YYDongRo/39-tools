from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.integrations.playwright import (
    RecordedPlaywrightExecutor,
    diagnose_playwright_click_failure,
    replay_playwright_session_action,
)
from agent_devtools.replay import replay_click, replay_fill
from agent_devtools.report import write_action_html
from agent_devtools.serialization import (
    read_action_json,
    read_session_json,
    write_action_json,
)


playwright = pytest.importorskip(
    "playwright.sync_api",
    reason="the browser replay test requires the browser extra",
)


def test_replays_saved_browser_click(tmp_path: Path) -> None:
    source_path = tmp_path / "original.json"
    replay_path = tmp_path / "replay.json"
    report_path = tmp_path / "report.html"
    before_path = tmp_path / "before.png"
    after_path = tmp_path / "after.png"
    page_path = (
        Path(__file__).parents[2] / "examples" / "browser_click.html"
    ).resolve()
    source_action = ActionRecord(
        action_type="click",
        arguments={"selector": "#agent-action"},
        start_time=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
        duration_ms=25,
        status=ActionStatus.SUCCESS,
    )
    write_action_json(source_action, source_path)
    loaded_action = read_action_json(source_path)

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 650})
        page.goto(page_path.as_uri())
        page.screenshot(path=str(before_path), full_page=True)

        def execute_click(selector: str, timeout_ms: int | None) -> None:
            if timeout_ms is None:
                page.locator(selector).click()
            else:
                page.locator(selector).click(timeout=timeout_ms)

        result = replay_click(
            loaded_action,
            execute_click,
            screenshot_before=Path("before.png"),
            screenshot_after=Path("after.png"),
        )

        page.screenshot(path=str(after_path), full_page=True)
        status_text = page.locator("#status").inner_text()
        browser.close()

    write_action_json(result.replayed_action, replay_path)
    write_action_html(result.replayed_action, report_path)

    assert result.outcome_matches
    assert result.replayed_action.status is ActionStatus.SUCCESS
    assert status_text == "The browser click succeeded."
    assert before_path.stat().st_size > 0
    assert after_path.stat().st_size > 0
    assert before_path.read_bytes() != after_path.read_bytes()
    assert read_action_json(replay_path) == result.replayed_action
    assert report_path.is_file()


def test_replays_saved_browser_fill(tmp_path: Path) -> None:
    source_path = tmp_path / "original.json"
    replay_path = tmp_path / "replay.json"
    report_path = tmp_path / "report.html"
    before_path = tmp_path / "before.png"
    after_path = tmp_path / "after.png"
    page_path = (
        Path(__file__).parents[2] / "examples" / "browser_diagnostics.html"
    ).resolve()
    source_action = ActionRecord(
        action_type="fill",
        arguments={
            "selector": "#visible-input",
            "text": "Agent debugging",
            "timeout_ms": 500,
        },
        start_time=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
        duration_ms=25,
        status=ActionStatus.SUCCESS,
    )
    write_action_json(source_action, source_path)
    loaded_action = read_action_json(source_path)

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 650})
        page.goto(page_path.as_uri())
        page.screenshot(path=str(before_path), full_page=True)

        def execute_fill(
            selector: str,
            text: str,
            timeout_ms: int | None,
        ) -> None:
            locator = page.locator(selector)
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

        page.screenshot(path=str(after_path), full_page=True)
        input_value = page.locator("#visible-input").input_value()
        browser.close()

    write_action_json(result.replayed_action, replay_path)
    write_action_html(result.replayed_action, report_path)

    assert result.outcome_matches
    assert result.replayed_action.status is ActionStatus.SUCCESS
    assert input_value == "Agent debugging"
    assert before_path.stat().st_size > 0
    assert after_path.stat().st_size > 0
    assert before_path.read_bytes() != after_path.read_bytes()
    assert read_action_json(replay_path) == result.replayed_action
    assert report_path.is_file()


def test_replays_browser_fill_with_navigation_context(tmp_path: Path) -> None:
    source_dir = tmp_path / "original"
    replay_dir = tmp_path / "replay"
    page_path = (
        Path(__file__).parents[2] / "examples" / "browser_diagnostics.html"
    ).resolve()

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        source_page = browser.new_page(viewport={"width": 1000, "height": 650})
        with RecordedPlaywrightExecutor(
            source_page,
            source_dir,
            goal="Open the diagnostics page and fill the missing input.",
        ) as executor:
            executor.navigate(page_path.as_uri())
            source_action = executor.fill(
                "#missing-input",
                "Agent debugging",
                timeout_ms=100,
            )
        source_page.close()

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
        browser.close()

    assert source_action.failure_category is FailureCategory.TARGET_NOT_FOUND
    assert result.context_failure_action_number is None
    assert result.target_result is not None
    assert (
        result.target_result.replayed_action.failure_category
        is FailureCategory.TARGET_NOT_FOUND
    )
    assert result.reproduced
    assert [action.action_type for action in result.replayed_session.actions] == [
        "navigate",
        "fill",
    ]
    report_content = (replay_dir / "report.html").read_text(encoding="utf-8")
    assert '<strong class="replay-verdict">Reproduced</strong>' in report_content
    assert (replay_dir / "report.html").is_file()
    assert (replay_dir / "actions/001/before.png").is_file()
    assert (replay_dir / "actions/002/after.png").is_file()


def test_replays_browser_timeout_failure() -> None:
    page_path = (
        Path(__file__).parents[2] / "examples" / "browser_click.html"
    ).resolve()
    source_action = ActionRecord(
        action_type="click",
        arguments={"selector": "#missing", "timeout_ms": 100},
        start_time=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
        duration_ms=100,
        status=ActionStatus.FAILURE,
        failure_reason="TimeoutError: original action timed out",
        failure_category=FailureCategory.TARGET_NOT_FOUND,
        failure_evidence={
            "selector": "#missing",
            "selector_count": 0,
            "target_visible": None,
            "target_enabled": None,
        },
    )

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(page_path.as_uri())

        def execute_click(selector: str, timeout_ms: int | None) -> None:
            page.locator(selector).click(timeout=timeout_ms)

        result = replay_click(
            source_action,
            execute_click,
            diagnose_failure=lambda action: diagnose_playwright_click_failure(
                page,
                action,
            ),
        )

        browser.close()

    assert result.replayed_action.status is ActionStatus.FAILURE
    assert result.replayed_action.failure_category is FailureCategory.TARGET_NOT_FOUND
    assert result.replayed_action.failure_evidence["selector_count"] == 0
    assert result.outcome_matches
