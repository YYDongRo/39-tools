from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from agent_devtools import ActionOutcome
from agent_devtools.playwright import (
    GeneratedTaskExpectation,
    TaskExpectation,
    all_of,
    element_visible,
    observe_async_playwright_agent,
    observe_playwright_agent,
    text_contains,
    url_matches,
)


if TYPE_CHECKING:
    from playwright.async_api import Page as AsyncPage
    from playwright.sync_api import Page


sync_playwright = pytest.importorskip("playwright.sync_api")
async_playwright = pytest.importorskip("playwright.async_api")
TARGET_URL = (
    Path(__file__).parents[2] / "examples" / "browser_diagnostics.html"
).resolve().as_uri()


class BrowserTools:
    def __init__(self, page: Page) -> None:
        self.page = page

    def navigate(self, url: str) -> None:
        self.page.goto(url)

    def click(self, selector: str) -> None:
        self.page.locator(selector).click()


class DemoAgent:
    def __init__(self) -> None:
        self.requests: list[str] = []

    def run(self, user_request: str, *, tools: BrowserTools) -> str:
        self.requests.append(user_request)
        tools.navigate(TARGET_URL)
        tools.click("#visible-target")
        return "agent result"


class FailingAgent:
    def run(self, user_request: str, *, tools: BrowserTools) -> None:
        tools.navigate(TARGET_URL)
        raise RuntimeError(f"agent failed while handling {user_request}")


class AsyncBrowserTools:
    def __init__(self, page: AsyncPage) -> None:
        self.page = page

    async def navigate(self, url: str) -> None:
        await self.page.goto(url)


class AsyncDemoAgent:
    async def run(
        self,
        user_request: str,
        *,
        tools: AsyncBrowserTools,
    ) -> str:
        await tools.navigate(TARGET_URL)
        return f"handled: {user_request}"


def _expectation_for_request(user_request: str) -> TaskExpectation:
    assert user_request
    return all_of(
        url_matches(scheme="file"),
        element_visible("#visible-target"),
        text_contains("h1", "Browser action diagnostics"),
    )


def _generated_expectation_for_request(
    user_request: str,
) -> GeneratedTaskExpectation:
    return GeneratedTaskExpectation(
        expectation=_expectation_for_request(user_request),
        inferred_goal="Open the local diagnostics page and click its target",
        source="openai:test-model",
    )


def test_observed_agent_captures_request_and_writes_verified_report(
    tmp_path: Path,
) -> None:
    user_request = "Open the browser diagnostics and click the visible target"
    with sync_playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        raw_agent = DemoAgent()
        observed_agent = observe_playwright_agent(
            raw_agent,
            BrowserTools(page),
            page,
            tmp_path / "runs",
            expectation_generator=_generated_expectation_for_request,
        )

        result = observed_agent.run(user_request)
        observed_agent.assert_last_task_passed()
        browser.close()

    assert result == "agent result"
    assert raw_agent.requests == [user_request]
    assert observed_agent.last_trace is not None
    assert observed_agent.last_trace.session.goal == user_request
    assert observed_agent.last_trace.session.inferred_goal == (
        "Open the local diagnostics page and click its target"
    )
    assert observed_agent.last_trace.session.verification_source == (
        "openai:test-model"
    )
    assert observed_agent.last_trace.session.outcome is ActionOutcome.SUCCESS
    assert [
        action.action_type
        for action in observed_agent.last_trace.session.actions
    ] == ["navigate", "click"]
    assert observed_agent.last_report_path is not None
    assert observed_agent.last_report_path.is_file()
    report = observed_agent.last_report_path.read_text(encoding="utf-8")
    assert user_request in report
    assert "Inferred goal" in report
    assert "openai:test-model" in report
    assert "<h3>Checks</h3>" in report


def test_observed_agent_creates_a_report_when_agent_raises(
    tmp_path: Path,
) -> None:
    with sync_playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        observed_agent = observe_playwright_agent(
            FailingAgent(),
            BrowserTools(page),
            page,
            tmp_path / "runs",
        )

        with pytest.raises(RuntimeError, match="agent failed"):
            observed_agent.run("Open the diagnostics page")
        browser.close()

    assert observed_agent.last_trace is not None
    assert observed_agent.last_trace.session.action_count == 1
    assert observed_agent.last_trace.session.outcome is ActionOutcome.UNVERIFIED
    assert observed_agent.last_report_path is not None
    assert observed_agent.last_report_path.is_file()


def test_observed_agent_creates_a_unique_trace_for_each_request(
    tmp_path: Path,
) -> None:
    with sync_playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        observed_agent = observe_playwright_agent(
            DemoAgent(),
            BrowserTools(page),
            page,
            tmp_path / "runs",
        )

        observed_agent.run("First request")
        first_report = observed_agent.last_report_path
        observed_agent.run("Second request")
        second_report = observed_agent.last_report_path
        browser.close()

    assert first_report is not None
    assert second_report is not None
    assert first_report != second_report
    assert first_report.is_file()
    assert second_report.is_file()
    assert observed_agent.last_trace is not None
    assert observed_agent.last_trace.session.goal == "Second request"


def test_expectation_generation_failure_does_not_stop_the_agent(
    tmp_path: Path,
) -> None:
    def fail_generation(user_request: str) -> TaskExpectation:
        raise RuntimeError(f"secret-provider-detail for {user_request}")

    with sync_playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        observed_agent = observe_playwright_agent(
            DemoAgent(),
            BrowserTools(page),
            page,
            tmp_path / "runs",
            expectation_generator=fail_generation,
        )

        result = observed_agent.run("Open the diagnostics page")
        browser.close()

    assert result == "agent result"
    assert observed_agent.last_trace is not None
    session = observed_agent.last_trace.session
    assert session.action_count == 2
    assert session.outcome is ActionOutcome.UNVERIFIED
    assert session.verification_source == "custom:function"
    assert session.verification_note is not None
    assert "RuntimeError" in session.verification_note
    assert "secret-provider-detail" not in session.verification_note
    assert observed_agent.last_report_path is not None
    report = observed_agent.last_report_path.read_text(encoding="utf-8")
    assert "Automatic verification was unavailable" in report
    assert "secret-provider-detail" not in report


def test_async_observed_agent_captures_the_same_request(
    tmp_path: Path,
) -> None:
    user_request = "Open the diagnostics page asynchronously"

    async def run() -> None:
        async with async_playwright.async_playwright() as browser_api:
            browser = await browser_api.chromium.launch(headless=True)
            page = await browser.new_page()
            observed_agent = observe_async_playwright_agent(
                AsyncDemoAgent(),
                AsyncBrowserTools(page),
                page,
                tmp_path / "runs",
                expectation_generator=_expectation_for_request,
            )

            result = await observed_agent.run(user_request)
            observed_agent.assert_last_task_passed()
            await browser.close()

        assert result == f"handled: {user_request}"
        assert observed_agent.last_trace is not None
        assert observed_agent.last_trace.session.goal == user_request
        assert observed_agent.last_report_path is not None
        assert observed_agent.last_report_path.is_file()

    asyncio.run(run())
