from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


class _PlaywrightEventCollectorBase:
    def __init__(
        self,
        page: object,
        *,
        settle_ms: int = 100,
        max_events: int = 20,
    ) -> None:
        if (
            not isinstance(settle_ms, int)
            or isinstance(settle_ms, bool)
            or settle_ms < 0
        ):
            raise ValueError("settle_ms must be a non-negative integer")
        if (
            not isinstance(max_events, int)
            or isinstance(max_events, bool)
            or max_events <= 0
        ):
            raise ValueError("max_events must be a positive integer")
        self.page = page
        self.settle_ms = settle_ms
        self.max_events = max_events
        self._events: list[dict[str, object]] = []
        self._dropped_count = 0
        self._listening = False

    def start(self) -> None:
        if self._listening:
            raise RuntimeError("browser event collection is already active")
        self._events = []
        self._dropped_count = 0
        self.page.on(  # type: ignore[attr-defined]
            "pageerror",
            self._on_page_error,
        )
        try:
            self.page.on(  # type: ignore[attr-defined]
                "console",
                self._on_console,
            )
        except Exception:
            self.page.remove_listener(  # type: ignore[attr-defined]
                "pageerror",
                self._on_page_error,
            )
            raise
        self._listening = True

    def _stop(self) -> list[dict[str, object]]:
        if not self._listening:
            return []
        try:
            self.page.remove_listener(  # type: ignore[attr-defined]
                "pageerror",
                self._on_page_error,
            )
        finally:
            try:
                self.page.remove_listener(  # type: ignore[attr-defined]
                    "console",
                    self._on_console,
                )
            finally:
                self._listening = False
        events = [dict(event) for event in self._events]
        if self._dropped_count:
            events.append(
                {
                    "event_type": "events_dropped",
                    "count": self._dropped_count,
                }
            )
        return events

    def _on_page_error(self, error: object) -> None:
        self._add_event(
            {
                "event_type": "page_error",
                "message": _bounded_message(str(error)),
                "url": _safe_url(self.page.url),  # type: ignore[attr-defined]
                "count": 1,
            }
        )

    def _on_console(self, message: object) -> None:
        if getattr(message, "type", None) != "error":
            return
        location = getattr(message, "location", {})
        if not isinstance(location, dict):
            location = {}
        event: dict[str, object] = {
            "event_type": "console_error",
            "message": _bounded_message(str(getattr(message, "text", ""))),
            "count": 1,
        }
        url = location.get("url")
        if isinstance(url, str) and url:
            event["url"] = _safe_url(url)
        line_number = location.get("lineNumber")
        if isinstance(line_number, int):
            event["line_number"] = line_number
        column_number = location.get("columnNumber")
        if isinstance(column_number, int):
            event["column_number"] = column_number
        self._add_event(event)

    def _add_event(self, event: dict[str, object]) -> None:
        comparable = {key: value for key, value in event.items() if key != "count"}
        for existing in self._events:
            existing_comparable = {
                key: value
                for key, value in existing.items()
                if key != "count"
            }
            if comparable == existing_comparable:
                count = existing.get("count", 1)
                existing["count"] = count + 1 if isinstance(count, int) else 2
                return
        if len(self._events) >= self.max_events:
            self._dropped_count += 1
            return
        self._events.append(event)


class PlaywrightEventCollector(_PlaywrightEventCollectorBase):
    def finish(self) -> list[dict[str, object]]:
        try:
            if self.settle_ms:
                self.page.wait_for_timeout(  # type: ignore[attr-defined]
                    self.settle_ms
                )
        finally:
            events = self._stop()
        return events


class AsyncPlaywrightEventCollector(_PlaywrightEventCollectorBase):
    async def finish(self) -> list[dict[str, object]]:
        try:
            if self.settle_ms:
                await self.page.wait_for_timeout(  # type: ignore[attr-defined]
                    self.settle_ms
                )
        finally:
            events = self._stop()
        return events


def _safe_url(url: object) -> str:
    if not isinstance(url, str):
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _bounded_message(message: str, limit: int = 1_000) -> str:
    if len(message) <= limit:
        return message
    return f"{message[:limit]}…"
