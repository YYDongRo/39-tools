import asyncio
from collections.abc import Callable

import pytest

from agent_devtools.integrations.playwright_events import (
    AsyncPlaywrightEventCollector,
    PlaywrightEventCollector,
)


class FakePage:
    def __init__(self) -> None:
        self.url = "https://example.com/video?token=secret#player"
        self.handlers: dict[str, list[Callable[[object], None]]] = {}
        self.waited_ms: list[int] = []

    def on(self, name: str, handler: Callable[[object], None]) -> None:
        self.handlers.setdefault(name, []).append(handler)

    def remove_listener(
        self,
        name: str,
        handler: Callable[[object], None],
    ) -> None:
        self.handlers[name].remove(handler)

    def emit(self, name: str, value: object) -> None:
        for handler in list(self.handlers.get(name, [])):
            handler(value)

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.waited_ms.append(milliseconds)


class FakeAsyncPage(FakePage):
    async def wait_for_timeout(self, milliseconds: int) -> None:
        await asyncio.sleep(0)
        self.waited_ms.append(milliseconds)


class FakeConsoleMessage:
    def __init__(
        self,
        message_type: str,
        text: str,
        *,
        url: str = "https://example.com/app.js?token=secret",
    ) -> None:
        self.type = message_type
        self.text = text
        self.location = {
            "url": url,
            "lineNumber": 12,
            "columnNumber": 8,
        }


class FakeRequest:
    def __init__(
        self,
        url: str,
        *,
        method: str = "GET",
        resource_type: str = "fetch",
        failure: str | None = None,
    ) -> None:
        self.url = url
        self.method = method
        self.resource_type = resource_type
        self.failure = failure


class FakeResponse:
    def __init__(self, status: int, request: FakeRequest) -> None:
        self.status = status
        self.request = request
        self.url = request.url


def test_collects_deduplicates_and_sanitizes_browser_errors() -> None:
    page = FakePage()
    collector = PlaywrightEventCollector(
        page,
        settle_ms=25,
        max_events=5,
    )
    collector.start()

    page.emit("console", FakeConsoleMessage("log", "ignored"))
    page.emit("console", FakeConsoleMessage("error", "service failed"))
    page.emit("console", FakeConsoleMessage("error", "service failed"))
    page.emit("pageerror", RuntimeError("player failed"))
    events = collector.finish()

    assert page.waited_ms == [25]
    assert events == [
        {
            "event_type": "console_error",
            "message": "service failed",
            "count": 2,
            "url": "https://example.com/app.js",
            "line_number": 12,
            "column_number": 8,
        },
        {
            "event_type": "page_error",
            "message": "player failed",
            "url": "https://example.com/video",
            "count": 1,
        },
    ]
    assert page.handlers == {
        "pageerror": [],
        "console": [],
        "requestfailed": [],
        "response": [],
    }


def test_collects_failed_requests_and_http_errors_without_sensitive_url_data(
) -> None:
    page = FakePage()
    collector = PlaywrightEventCollector(page, settle_ms=0)
    collector.start()
    request = FakeRequest(
        "https://user:password@example.com/api/search?token=secret#result",
        method="POST",
        resource_type="xhr",
    )

    page.emit("response", FakeResponse(200, request))
    page.emit("response", FakeResponse(503, request))
    page.emit(
        "requestfailed",
        FakeRequest(
            "https://example.com/video?id=secret",
            resource_type="media",
            failure="net::ERR_CONNECTION_RESET",
        ),
    )

    assert collector.finish() == [
        {
            "event_type": "http_error",
            "message": "POST xhr request returned HTTP 503",
            "method": "POST",
            "resource_type": "xhr",
            "url": "https://example.com/api/search",
            "status": 503,
            "count": 1,
        },
        {
            "event_type": "request_failed",
            "message": (
                "GET media request failed: net::ERR_CONNECTION_RESET"
            ),
            "method": "GET",
            "resource_type": "media",
            "url": "https://example.com/video",
            "failure": "net::ERR_CONNECTION_RESET",
            "count": 1,
        },
    ]


def test_redacts_data_url_content() -> None:
    page = FakePage()
    collector = PlaywrightEventCollector(page, settle_ms=0)
    collector.start()
    page.emit(
        "requestfailed",
        FakeRequest(
            "data:text/plain,private-content",
            failure="net::ERR_FAILED",
        ),
    )

    events = collector.finish()

    assert events[0]["url"] == "data:"
    assert "private-content" not in str(events)


def test_caps_unique_events_and_reports_dropped_count() -> None:
    page = FakePage()
    collector = PlaywrightEventCollector(page, settle_ms=0, max_events=1)
    collector.start()

    page.emit("console", FakeConsoleMessage("error", "first"))
    page.emit("console", FakeConsoleMessage("error", "second"))
    events = collector.finish()

    assert events[0]["message"] == "first"
    assert events[1] == {"event_type": "events_dropped", "count": 1}


def test_async_collector_waits_and_returns_events() -> None:
    async def run() -> None:
        page = FakeAsyncPage()
        collector = AsyncPlaywrightEventCollector(page, settle_ms=10)
        collector.start()
        page.emit("pageerror", RuntimeError("async player failed"))
        page.emit(
            "response",
            FakeResponse(
                429,
                FakeRequest(
                    "https://example.com/api?key=secret",
                    resource_type="fetch",
                ),
            ),
        )

        events = await collector.finish()

        assert page.waited_ms == [10]
        assert events[0]["message"] == "async player failed"
        assert events[1]["message"] == "GET fetch request returned HTTP 429"

    asyncio.run(run())


@pytest.mark.parametrize(
    ("keyword", "value", "message"),
    [
        ("settle_ms", -1, "settle_ms must be"),
        ("settle_ms", True, "settle_ms must be"),
        ("max_events", 0, "max_events must be"),
        ("max_events", True, "max_events must be"),
    ],
)
def test_rejects_invalid_limits(
    keyword: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        PlaywrightEventCollector(
            FakePage(),
            **{keyword: value},  # type: ignore[arg-type]
        )
