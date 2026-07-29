from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from agent_devtools import ActionOutcome, ActionStatus
from agent_devtools.analysis import analyze_session
from agent_devtools.failure import FailureCategory
from agent_devtools.integrations.playwright import (
    expect_text,
    run_playwright_agent,
)
from agent_devtools.playwright import (
    InputValueExpectation,
    PlaywrightAction,
    RecordedPlaywrightExecutor,
    TextExpectation,
    VisibilityExpectation,
    record_playwright_tools,
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
        return PlaywrightAction(
            "click",
            {"selector": "#search-button"},
            expectation=TextExpectation("#video-result", expected_result),
        )

    if not page.locator("#player").is_visible():
        return PlaywrightAction(
            "click",
            {"selector": "#video-result"},
            expectation=VisibilityExpectation("#player"),
        )

    if page.locator("#player-status").inner_text() != EXPECTED_PLAYER_STATUS:
        return PlaywrightAction(
            "click",
            {"selector": "#play"},
            expectation=TextExpectation(
                "#player-status",
                EXPECTED_PLAYER_STATUS,
            ),
        )

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
        with RecordedPlaywrightExecutor(
            page,
            trace_dir,
            goal="Search for 'Agent debugging' and play the result",
            task_verification=task_verification,
        ) as executor:
            recorded_actions = executor.run(decide_next_action)
        session = executor.session

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
    navigation_verification = session.actions[0].verification
    assert navigation_verification is not None
    assert navigation_verification.passed
    assert navigation_verification.evidence == {
        "expectation_type": "element_visible",
        "selector": "#search",
        "selector_count": 1,
        "target_visible": True,
        "timeout_ms": 2_000,
        "url": TARGET_URL,
    }
    assert session.actions[1].verification is None
    assert session.actions[1].observations == {
        "page_url_before": TARGET_URL,
        "input_value_after": SEARCH_QUERY,
        "page_url_after": TARGET_URL,
    }
    assert session.actions[0].observations == {
        "page_url_before": "about:blank",
        "page_url_after": TARGET_URL,
    }
    assert all(
        action.verification is not None
        and action.verification.passed
        for action in session.actions[2:]
    )
    assert [
        action.verification.evidence["expectation_type"]
        for action in session.actions
        if action.verification is not None
    ] == [
        "element_visible",
        "text_equals",
        "element_visible",
        "text_equals",
    ]
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
    assert "Final checks" in report
    assert '<strong class="result-title">Successful</strong>' in report
    assert '<span>Actions</span><strong>5</strong>' in report
    assert "&#x27;#search&#x27; is visible" in report
    assert "Observations" in report
    assert "<dt>Input value after</dt><dd>Agent debugging</dd>" in report


def test_executor_records_direct_playwright_actions(tmp_path: Path) -> None:
    trace_dir = tmp_path / "direct-executor"

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()

        with RecordedPlaywrightExecutor(page, trace_dir) as executor:
            navigate = executor.navigate(
                TARGET_URL,
                expectation=VisibilityExpectation("#search"),
            )
            fill = executor.fill("#search", SEARCH_QUERY)
            search = executor.click(
                "#search-button",
                expectation=TextExpectation(
                    "#video-result",
                    f"Result for: {SEARCH_QUERY}",
                ),
            )

        browser.close()

    assert executor.session.actions == [navigate, fill, search]
    assert [action.action_type for action in executor.session.actions] == [
        "navigate",
        "fill",
        "click",
    ]
    assert navigate.observations == {
        "page_url_before": "about:blank",
        "page_url_after": TARGET_URL,
    }
    assert fill.observations == {
        "page_url_before": TARGET_URL,
        "input_value_after": SEARCH_QUERY,
        "page_url_after": TARGET_URL,
    }
    assert search.observations == {
        "page_url_before": TARGET_URL,
        "page_url_after": TARGET_URL,
    }
    assert navigate.verification is not None
    assert navigate.verification.passed
    assert search.verification is not None
    assert search.verification.passed
    assert executor.report_path == trace_dir / "report.html"
    assert executor.report_path.is_file()


def test_executor_records_press_and_scroll_actions(tmp_path: Path) -> None:
    trace_dir = tmp_path / "press-and-scroll"

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 800, "height": 500})
        page.set_content(
            """
            <input id="search" onkeydown="document.body.dataset.key = event.key">
            <div style="height: 2000px"></div>
            """
        )

        with RecordedPlaywrightExecutor(page, trace_dir) as executor:
            pressed = executor.press("#search", "Enter")
            scrolled = executor.scroll(delta_y=600)

        pressed_key = page.locator("body").get_attribute("data-key")
        scroll_y = page.evaluate("() => window.scrollY")
        browser.close()

    assert pressed_key == "Enter"
    assert scroll_y > 0
    assert executor.session.actions == [pressed, scrolled]
    assert pressed.arguments == {"selector": "#search", "key": "Enter"}
    assert pressed.status is ActionStatus.SUCCESS
    assert scrolled.arguments == {"delta_x": 0, "delta_y": 600}
    assert scrolled.status is ActionStatus.SUCCESS
    assert scrolled.observations["scroll_before"]["y"] == 0
    assert scrolled.observations["scroll_after"]["y"] > 0
    for action_number in range(1, 3):
        action_dir = trace_dir / "actions" / f"{action_number:03d}"
        assert (action_dir / "before.png").stat().st_size > 0
        assert (action_dir / "after.png").stat().st_size > 0


def test_executor_diagnoses_failed_press_target(tmp_path: Path) -> None:
    trace_dir = tmp_path / "failed-press"

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("<button id='available'>Available</button>")

        with RecordedPlaywrightExecutor(page, trace_dir) as executor:
            action = executor.press("#missing", "Enter", timeout_ms=100)

        browser.close()

    assert action.status is ActionStatus.FAILURE
    assert action.failure_category is FailureCategory.TARGET_NOT_FOUND
    assert action.failure_evidence == {
        "selector": "#missing",
        "selector_count": 0,
        "target_visible": None,
        "target_enabled": None,
    }


def test_playwright_tool_wrapper_records_calls_and_structured_state(
    tmp_path: Path,
) -> None:
    class BrowserTools:
        def __init__(self, page: Page) -> None:
            self.page = page

        def navigate(self, url: str) -> None:
            self.page.goto(url)

        def fill(self, selector: str, text: str) -> None:
            self.page.locator(selector).fill(text)

        def click(self, selector: str) -> None:
            self.page.locator(selector).click()

    trace_dir = tmp_path / "wrapped-tools"

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 700})
        trace = record_playwright_tools(
            BrowserTools(page),
            page,
            trace_dir,
        )

        with trace as tools:
            tools.navigate(TARGET_URL)
            tools.fill("#search", SEARCH_QUERY)
            tools.click("#search-button")

        browser.close()

    assert [action.action_type for action in trace.session.actions] == [
        "navigate",
        "fill",
        "click",
    ]
    assert trace.session.actions[1].arguments == {
        "selector": "#search",
        "text": SEARCH_QUERY,
    }
    assert all(
        action.status is ActionStatus.SUCCESS
        for action in trace.session.actions
    )
    navigation_observations = trace.session.actions[0].observations
    state_before = navigation_observations["state_before"]
    state_after = navigation_observations["state_after"]
    assert isinstance(state_before, dict)
    assert isinstance(state_after, dict)
    assert state_before["url"] == "about:blank"
    assert state_after["url"] == TARGET_URL
    assert state_after["title"] == "Local Video Search"
    assert state_after["ready_state"] == "complete"
    assert state_after["visibility_state"] == "visible"
    assert state_after["viewport"] == {"width": 1000, "height": 700}
    assert isinstance(state_after["element_count"], int)
    assert {"title", "url"}.issubset(
        navigation_observations["state_changes"]
    )

    fill_observations = trace.session.actions[1].observations
    assert SEARCH_QUERY not in repr(fill_observations["state_after"])
    assert "focused_element" in fill_observations["state_changes"]
    assert trace.report_path.is_file()
    for action_number in range(1, 4):
        action_dir = trace_dir / "actions" / f"{action_number:03d}"
        assert (action_dir / "before.png").stat().st_size > 0
        assert (action_dir / "after.png").stat().st_size > 0


def test_playwright_tool_wrapper_rejects_invalid_screenshot_mode(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        TypeError,
        match="full_page_screenshots must be a boolean",
    ):
        record_playwright_tools(
            object(),
            object(),  # type: ignore[arg-type]
            tmp_path / "trace",
            full_page_screenshots="yes",  # type: ignore[arg-type]
        )


def test_playwright_tool_wrapper_captures_page_error_likely_cause(
    tmp_path: Path,
) -> None:
    class BrowserTools:
        def __init__(self, page: Page) -> None:
            self.page = page

        def click(self, selector: str) -> None:
            self.page.locator(selector).click()

    diagnostics_url = (
        Path(__file__).parents[2] / "examples" / "browser_diagnostics.html"
    ).resolve().as_uri()
    trace_dir = tmp_path / "browser-page-error"

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(diagnostics_url)
        trace = record_playwright_tools(
            BrowserTools(page),
            page,
            trace_dir,
        )

        with trace as tools:
            tools.click("#error-target")

        browser.close()

    action = trace.session.actions[0]
    assert action.status is ActionStatus.SUCCESS
    browser_events = action.observations["browser_events"]
    assert isinstance(browser_events, list)
    assert {
        event["event_type"]
        for event in browser_events
        if isinstance(event, dict)
    } == {"console_error", "page_error"}
    findings = analyze_session(trace.session)
    assert len(findings) == 1
    assert findings[0].code == "page_error_during_action"
    assert findings[0].action_numbers == (1,)
    assert "player initialization failed" in (
        findings[0].likely_cause or ""
    )

    report = trace.report_path.read_text(encoding="utf-8")
    assert "Page error during action" in report
    assert "<strong>Likely cause:</strong> player initialization failed" in report
    assert "Browser evidence (2 events)" in report


def test_navigation_visibility_expectation_reports_missing_element(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "missing-navigation-marker"
    decisions = iter(
        [
            PlaywrightAction(
                "navigate",
                {"url": TARGET_URL},
                expectation=VisibilityExpectation(
                    "#missing-page-marker",
                    timeout_ms=100,
                ),
            ),
            None,
        ]
    )

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()

        with SessionRecorder(
            trace_dir,
            lambda path: page.screenshot(path=str(path), full_page=True),
        ) as recorder:
            recorded_actions = run_playwright_agent(
                page,
                recorder,
                lambda page: next(decisions),
            )

        browser.close()

    action = recorded_actions[0]
    assert action.status is ActionStatus.SUCCESS
    assert action.outcome is ActionOutcome.FAILURE
    assert action.verification is not None
    assert not action.verification.passed
    assert action.verification.observed_state == "0 matching elements"
    assert action.verification.failure_reason == (
        "expected selector '#missing-page-marker' to match exactly one "
        "element, observed 0"
    )
    assert action.verification.evidence["url"] == TARGET_URL


def test_dynamic_text_expectation_reports_mismatch(tmp_path: Path) -> None:
    trace_dir = tmp_path / "text-mismatch"
    decisions = iter(
        [
            PlaywrightAction(
                "click",
                {"selector": "#search-button"},
                expectation=TextExpectation(
                    "#video-result",
                    "Unexpected result",
                    timeout_ms=100,
                ),
            ),
            None,
        ]
    )

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(TARGET_URL)
        page.locator("#search").fill(SEARCH_QUERY)

        with SessionRecorder(trace_dir) as recorder:
            recorded_actions = run_playwright_agent(
                page,
                recorder,
                lambda page: next(decisions),
            )

        browser.close()

    action = recorded_actions[0]
    assert action.status is ActionStatus.SUCCESS
    assert action.outcome is ActionOutcome.FAILURE
    assert action.verification is not None
    assert not action.verification.passed
    assert action.verification.expected_state == "Unexpected result"
    assert action.verification.observed_state == (
        f"Result for: {SEARCH_QUERY}"
    )


def test_fill_can_optionally_verify_exact_input_value(tmp_path: Path) -> None:
    trace_dir = tmp_path / "exact-input"
    decisions = iter(
        [
            PlaywrightAction(
                "fill",
                {"selector": "#search", "text": SEARCH_QUERY},
                expectation=InputValueExpectation(),
            ),
            None,
        ]
    )

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(TARGET_URL)

        with SessionRecorder(trace_dir) as recorder:
            recorded_actions = run_playwright_agent(
                page,
                recorder,
                lambda page: next(decisions),
            )

        browser.close()

    action = recorded_actions[0]
    assert action.observations == {
        "page_url_before": TARGET_URL,
        "input_value_after": SEARCH_QUERY,
        "page_url_after": TARGET_URL,
    }
    assert action.verification is not None
    assert action.verification.passed
    assert action.outcome is ActionOutcome.SUCCESS


def test_fill_exact_verification_reports_formatted_value(
    tmp_path: Path,
) -> None:
    trace_dir = tmp_path / "formatted-input"
    decisions = iter(
        [
            PlaywrightAction(
                "fill",
                {"selector": "#search", "text": SEARCH_QUERY},
                expectation=InputValueExpectation(timeout_ms=100),
            ),
            None,
        ]
    )

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(TARGET_URL)
        page.locator("#search").evaluate(
            """
            element => element.addEventListener(
                "input",
                () => { element.value = element.value.toUpperCase(); },
            )
            """
        )

        with SessionRecorder(trace_dir) as recorder:
            recorded_actions = run_playwright_agent(
                page,
                recorder,
                lambda page: next(decisions),
            )

        browser.close()

    action = recorded_actions[0]
    assert action.status is ActionStatus.SUCCESS
    assert action.observations == {
        "page_url_before": TARGET_URL,
        "input_value_after": SEARCH_QUERY.upper(),
        "page_url_after": TARGET_URL,
    }
    assert action.verification is not None
    assert not action.verification.passed
    assert action.verification.expected_state == SEARCH_QUERY
    assert action.verification.observed_state == SEARCH_QUERY.upper()


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
