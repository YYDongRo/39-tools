from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from agent_devtools.playwright import (
    TaskExpectation,
    all_of,
    element_visible,
    property_equals,
    record_async_playwright_tools,
    record_playwright_tools,
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


class AsyncBrowserTools:
    def __init__(self, page: AsyncPage) -> None:
        self.page = page

    async def navigate(self, url: str) -> None:
        await self.page.goto(url)


def _successful_expectation() -> TaskExpectation:
    return all_of(
        url_matches(scheme="file"),
        element_visible("#visible-target"),
        text_contains("h1", "Browser action diagnostics"),
        property_equals("#readonly-input", "readOnly", True),
    )


def test_sync_recorder_runs_declarative_task_expectation(
    tmp_path: Path,
) -> None:
    with sync_playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        trace = record_playwright_tools(
            BrowserTools(page),
            page,
            tmp_path / "trace",
            goal="open the diagnostics page",
            task_expectation=_successful_expectation(),
        )

        with trace as tools:
            tools.navigate(TARGET_URL)

        trace.assert_task_passed()
        browser.close()

    assert trace.session.verification is not None
    assert trace.session.verification.passed
    report = trace.report_path.read_text(encoding="utf-8")
    assert "<h3>Checks</h3>" in report
    assert report.count('class="verification-check ') == 4
    assert "Full verification evidence" in report


def test_sync_assertion_points_to_failed_task_report(tmp_path: Path) -> None:
    with sync_playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        trace = record_playwright_tools(
            BrowserTools(page),
            page,
            tmp_path / "trace",
            goal="show a missing result",
            task_expectation=text_contains(
                "h1",
                "Missing result",
                timeout_ms=100,
            ),
        )

        with trace as tools:
            tools.navigate(TARGET_URL)

        with pytest.raises(
            AssertionError,
            match="Task verification failed",
        ) as error:
            trace.assert_task_passed()
        browser.close()

    assert str(trace.report_path.resolve()) in str(error.value)
    assert trace.session.verification is not None
    assert not trace.session.verification.passed
    report = trace.report_path.read_text(encoding="utf-8")
    assert "<h3>Checks</h3>" in report
    assert report.count('class="verification-check ') == 1


def test_async_recorder_runs_same_declarative_expectation(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        async with async_playwright.async_playwright() as browser_api:
            browser = await browser_api.chromium.launch(headless=True)
            page = await browser.new_page()
            trace = record_async_playwright_tools(
                AsyncBrowserTools(page),
                page,
                tmp_path / "trace",
                goal="open the diagnostics page",
                task_expectation=_successful_expectation(),
            )

            async with trace as tools:
                await tools.navigate(TARGET_URL)

            trace.assert_task_passed()
            await browser.close()

        assert trace.session.verification is not None
        assert trace.session.verification.passed

    asyncio.run(run())
