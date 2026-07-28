from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from agent_devtools import (
    ActionOutcome,
    ActionStatus,
    VerificationResult,
    analyze_session,
    record_async_tools,
)
from agent_devtools.serialization import read_session_json
from agent_devtools.playwright import record_async_playwright_tools


if TYPE_CHECKING:
    from playwright.async_api import Page


playwright = pytest.importorskip(
    "playwright.async_api",
    reason="the async trajectory test requires the browser extra",
)

SEARCH_QUERY = "Agent debugging"
EXPECTED_RESULT = f"Result for: {SEARCH_QUERY}"
TARGET_URL = (
    Path(__file__).parents[2] / "examples" / "video_search_agent.html"
).resolve().as_uri()
DIAGNOSTICS_URL = (
    Path(__file__).parents[2] / "examples" / "browser_diagnostics.html"
).resolve().as_uri()


class AsyncBrowserTools:
    def __init__(self, page: Page) -> None:
        self.page = page

    async def navigate(self, url: str) -> None:
        await self.page.goto(url)

    async def fill(self, selector: str, text: str) -> None:
        await self.page.locator(selector).fill(text)

    async def click(self, selector: str) -> None:
        await self.page.locator(selector).click()


def test_records_real_async_browser_trajectory(tmp_path: Path) -> None:
    async def run() -> None:
        trace_dir = tmp_path / "async-browser-trajectory"

        async with playwright.async_playwright() as browser_api:
            browser = await browser_api.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={"width": 1000, "height": 700}
            )

            async def capture_screenshot(path: Path) -> None:
                await page.screenshot(path=str(path))

            async def observe_state() -> dict[str, object]:
                return await page.evaluate(
                    """
                    () => {
                        const search = document.querySelector("#search");
                        const results = document.querySelector("#results");
                        const result = document.querySelector("#video-result");
                        return {
                            url: window.location.href,
                            title: document.title,
                            search_value: search?.value ?? null,
                            result_visible: results?.hidden === false,
                            result_text: result?.textContent ?? "",
                        };
                    }
                    """
                )

            async def verify_task() -> VerificationResult:
                observed = await page.locator("#video-result").inner_text()
                passed = observed == EXPECTED_RESULT
                return VerificationResult(
                    expected_state=EXPECTED_RESULT,
                    observed_state=observed,
                    passed=passed,
                    failure_reason=(
                        None
                        if passed
                        else "the search result text did not match"
                    ),
                )

            trace = record_async_tools(
                AsyncBrowserTools(page),
                trace_dir,
                capture_screenshot=capture_screenshot,
                observe_state=observe_state,
                goal="search for Agent debugging",
                task_verification=verify_task,
            )

            async with trace as tools:
                await tools.navigate(TARGET_URL)
                await tools.fill("#search", SEARCH_QUERY)
                await tools.click("#search-button")

            await browser.close()

        assert [
            action.action_type for action in trace.session.actions
        ] == ["navigate", "fill", "click"]
        assert trace.session.actions[1].arguments == {
            "selector": "#search",
            "text": SEARCH_QUERY,
        }
        assert all(
            action.status is ActionStatus.SUCCESS
            for action in trace.session.actions
        )

        navigation = trace.session.actions[0]
        assert navigation.observations["state_before"] == {
            "url": "about:blank",
            "title": "",
            "search_value": None,
            "result_visible": False,
            "result_text": "",
        }
        navigation_after = navigation.observations["state_after"]
        assert isinstance(navigation_after, dict)
        assert navigation_after["url"] == TARGET_URL
        assert navigation_after["title"] == "Local Video Search"

        fill = trace.session.actions[1]
        assert fill.observations["state_changes"] == ["search_value"]
        click = trace.session.actions[2]
        assert click.observations["state_changes"] == [
            "result_text",
            "result_visible",
        ]

        assert trace.session.verification is not None
        assert trace.session.verification.passed
        assert trace.session.outcome is ActionOutcome.SUCCESS
        assert read_session_json(trace_dir / "session.json") == trace.session
        assert trace.report_path.is_file()

        for action_number in range(1, 4):
            action_dir = trace_dir / "actions" / f"{action_number:03d}"
            assert (action_dir / "before.png").stat().st_size > 0
            assert (action_dir / "after.png").stat().st_size > 0

        report = trace.report_path.read_text(encoding="utf-8")
        assert "search for Agent debugging" in report
        assert EXPECTED_RESULT in report
        assert "task successful" in report
        assert "3 actions" in report

    asyncio.run(run())


def test_real_browser_stuck_loop_appears_in_report(tmp_path: Path) -> None:
    async def run() -> None:
        trace_dir = tmp_path / "async-browser-stuck-loop"

        async with playwright.async_playwright() as browser_api:
            browser = await browser_api.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={"width": 1000, "height": 700}
            )

            async def capture_screenshot(path: Path) -> None:
                await page.screenshot(path=str(path))

            async def observe_state() -> dict[str, object]:
                return await page.evaluate(
                    """
                    () => ({
                        url: window.location.href,
                        title: document.title,
                        heading:
                            document.querySelector("h1")?.textContent ?? "",
                        target_exists:
                            document.querySelector("#visible-target") !== null,
                    })
                    """
                )

            trace = record_async_tools(
                AsyncBrowserTools(page),
                trace_dir,
                capture_screenshot=capture_screenshot,
                observe_state=observe_state,
            )

            async with trace as tools:
                await tools.navigate(DIAGNOSTICS_URL)
                for _ in range(3):
                    await tools.click("#visible-target")

            await browser.close()

        assert [
            action.action_type for action in trace.session.actions
        ] == ["navigate", "click", "click", "click"]
        assert all(
            action.status is ActionStatus.SUCCESS
            for action in trace.session.actions
        )
        assert all(
            action.observations["state_changes"] == []
            for action in trace.session.actions[1:]
        )

        findings = analyze_session(trace.session)
        assert len(findings) == 1
        assert findings[0].code == "possible_stuck_loop"
        assert findings[0].action_numbers == (2, 3, 4)
        assert findings[0].evidence == {
            "action_type": "click",
            "arguments": {"selector": "#visible-target"},
            "repeat_count": 3,
        }

        assert read_session_json(trace_dir / "session.json") == trace.session
        for action_number in range(1, 5):
            action_dir = trace_dir / "actions" / f"{action_number:03d}"
            assert (action_dir / "before.png").stat().st_size > 0
            assert (action_dir / "after.png").stat().st_size > 0

        report = trace.report_path.read_text(encoding="utf-8")
        assert '<h2 id="findings-title">Potential issues</h2>' in report
        assert '<span class="findings-count">1 warning</span>' in report
        assert "Possible stuck loop" in report
        assert (
            "Actions 2–4 repeated &#x27;click&#x27; with identical arguments, "
            "but the observed state did not change."
        ) in report
        assert '<a href="#action-2">Action 2</a>' in report
        assert '<a href="#action-4">Action 4</a>' in report

    asyncio.run(run())


def test_async_playwright_wrapper_captures_page_error_cause(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        trace_dir = tmp_path / "async-browser-page-error"

        async with playwright.async_playwright() as browser_api:
            browser = await browser_api.chromium.launch(headless=True)
            page = await browser.new_page(
                viewport={"width": 1000, "height": 700}
            )
            trace = record_async_playwright_tools(
                AsyncBrowserTools(page),
                page,
                trace_dir,
            )

            async with trace as tools:
                await tools.navigate(DIAGNOSTICS_URL)
                await tools.click("#error-target")

            await browser.close()

        click = trace.session.actions[1]
        assert click.status is ActionStatus.SUCCESS
        browser_events = click.observations["browser_events"]
        assert isinstance(browser_events, list)
        assert {
            event["event_type"]
            for event in browser_events
            if isinstance(event, dict)
        } == {"console_error", "page_error"}

        findings = analyze_session(trace.session)
        assert len(findings) == 1
        assert findings[0].code == "page_error_during_action"
        assert findings[0].action_numbers == (2,)
        assert "player initialization failed" in (
            findings[0].likely_cause or ""
        )

        assert read_session_json(trace_dir / "session.json") == trace.session
        for action_number in range(1, 3):
            action_dir = trace_dir / "actions" / f"{action_number:03d}"
            assert (action_dir / "before.png").stat().st_size > 0
            assert (action_dir / "after.png").stat().st_size > 0

        report = trace.report_path.read_text(encoding="utf-8")
        assert "Page error during action" in report
        assert (
            "<strong>Likely cause:</strong> player initialization failed"
            in report
        )
        assert "Browser evidence (2 events)" in report

    asyncio.run(run())
