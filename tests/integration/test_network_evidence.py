from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from agent_devtools.analysis import analyze_session
from agent_devtools.playwright import (
    record_async_playwright_tools,
    record_playwright_tools,
)


if TYPE_CHECKING:
    from playwright.async_api import Page as AsyncPage
    from playwright.sync_api import Page


sync_playwright = pytest.importorskip("playwright.sync_api")
async_playwright = pytest.importorskip("playwright.async_api")

APP_URL = "https://agent-devtools.test/"
PAGE_HTML = """
<!doctype html>
<button id="request" onclick="fetch('/api/data').catch(() => {})">
  Send request
</button>
"""


class BrowserTools:
    def __init__(self, page: Page) -> None:
        self.page = page

    def click(self, selector: str) -> None:
        self.page.locator(selector).click()


class AsyncBrowserTools:
    def __init__(self, page: AsyncPage) -> None:
        self.page = page

    async def click(self, selector: str) -> None:
        await self.page.locator(selector).click()


def test_records_http_error_response_for_the_triggering_action(
    tmp_path: Path,
) -> None:
    def handle(route: object) -> None:
        request_url = route.request.url  # type: ignore[attr-defined]
        if request_url.endswith("/api/data"):
            route.fulfill(  # type: ignore[attr-defined]
                status=503,
                content_type="text/plain",
                body="unavailable",
            )
        else:
            route.fulfill(  # type: ignore[attr-defined]
                status=200,
                content_type="text/html",
                body=PAGE_HTML,
            )

    with sync_playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("**/*", handle)
        page.goto(APP_URL)
        trace = record_playwright_tools(
            BrowserTools(page),
            page,
            tmp_path / "http-error",
        )

        with trace as tools:
            tools.click("#request")

        browser.close()

    action = trace.session.actions[0]
    events = action.observations["browser_events"]
    assert isinstance(events, list)
    http_errors = [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("event_type") == "http_error"
    ]
    assert http_errors == [
        {
            "event_type": "http_error",
            "message": "GET fetch request returned HTTP 503",
            "method": "GET",
            "resource_type": "fetch",
            "url": "https://agent-devtools.test/api/data",
            "status": 503,
            "count": 1,
        }
    ]
    findings = analyze_session(trace.session)
    assert findings[0].code == "http_error_response"
    report = trace.report_path.read_text(encoding="utf-8")
    assert "HTTP error response during action" in report
    assert "GET fetch request returned HTTP 503" in report


def test_async_records_failed_request_for_the_triggering_action(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        async def handle(route: object) -> None:
            request_url = route.request.url  # type: ignore[attr-defined]
            if request_url.endswith("/api/data"):
                await route.abort("failed")  # type: ignore[attr-defined]
            else:
                await route.fulfill(  # type: ignore[attr-defined]
                    status=200,
                    content_type="text/html",
                    body=PAGE_HTML,
                )

        async with async_playwright.async_playwright() as browser_api:
            browser = await browser_api.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.route("**/*", handle)
            await page.goto(APP_URL)
            trace = record_async_playwright_tools(
                AsyncBrowserTools(page),
                page,
                tmp_path / "request-failed",
            )

            async with trace as tools:
                await tools.click("#request")

            await browser.close()

        action = trace.session.actions[0]
        events = action.observations["browser_events"]
        assert isinstance(events, list)
        failed_requests = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("event_type") == "request_failed"
        ]
        assert len(failed_requests) == 1
        assert failed_requests[0]["method"] == "GET"
        assert failed_requests[0]["resource_type"] == "fetch"
        assert failed_requests[0]["url"] == (
            "https://agent-devtools.test/api/data"
        )
        assert "ERR_FAILED" in str(failed_requests[0]["failure"])
        findings = analyze_session(trace.session)
        assert findings[0].code == "network_request_failed"
        report = trace.report_path.read_text(encoding="utf-8")
        assert "Network request failed during action" in report
        assert "GET fetch request failed" in report

    asyncio.run(run())
