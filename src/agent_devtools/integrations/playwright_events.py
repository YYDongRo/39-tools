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
        self._active_listeners: tuple[tuple[str, object], ...] = ()

    def start(self) -> None:
        if self._listening:
            raise RuntimeError("browser event collection is already active")
        self._events = []
        self._dropped_count = 0
        registered: list[tuple[str, object]] = []
        try:
            for event_name, handler in self._listeners():
                self.page.on(event_name, handler)  # type: ignore[attr-defined]
                registered.append((event_name, handler))
        except Exception:
            for event_name, handler in reversed(registered):
                self.page.remove_listener(  # type: ignore[attr-defined]
                    event_name,
                    handler,
                )
            raise
        self._active_listeners = tuple(registered)
        self._listening = True

    def _stop(self) -> list[dict[str, object]]:
        if not self._listening:
            return []
        removal_error: Exception | None = None
        for event_name, handler in reversed(self._active_listeners):
            try:
                self.page.remove_listener(  # type: ignore[attr-defined]
                    event_name,
                    handler,
                )
            except Exception as error:
                if removal_error is None:
                    removal_error = error
        self._listening = False
        self._active_listeners = ()
        events = [dict(event) for event in self._events]
        if self._dropped_count:
            events.append(
                {
                    "event_type": "events_dropped",
                    "count": self._dropped_count,
                }
            )
        if removal_error is not None:
            raise removal_error
        return events

    def _listeners(self) -> tuple[tuple[str, object], ...]:
        return (
            ("pageerror", self._on_page_error),
            ("console", self._on_console),
            ("requestfailed", self._on_request_failed),
            ("response", self._on_response),
        )

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

    def _on_request_failed(self, request: object) -> None:
        metadata = _request_metadata(request)
        failure = getattr(request, "failure", None)
        if not isinstance(failure, str) or not failure:
            failure = "unknown network error"
        failure = _bounded_message(failure)
        self._add_event(
            {
                "event_type": "request_failed",
                "message": (
                    f"{_request_label(metadata)} failed: {failure}"
                ),
                **metadata,
                "failure": failure,
                "count": 1,
            }
        )

    def _on_response(self, response: object) -> None:
        status = getattr(response, "status", None)
        if (
            not isinstance(status, int)
            or isinstance(status, bool)
            or status < 400
            or status > 599
        ):
            return
        request = getattr(response, "request", None)
        metadata = _request_metadata(request)
        response_url = _safe_url(getattr(response, "url", None))
        if response_url:
            metadata["url"] = response_url
        self._add_event(
            {
                "event_type": "http_error",
                "message": (
                    f"{_request_label(metadata)} returned HTTP {status}"
                ),
                **metadata,
                "status": status,
                "count": 1,
            }
        )

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
    if parts.scheme.lower() in {"data", "javascript"}:
        return f"{parts.scheme.lower()}:"
    hostname = parts.hostname or ""
    if ":" in hostname:
        hostname = f"[{hostname}]"
    try:
        port = parts.port
    except ValueError:
        port = None
    netloc = f"{hostname}:{port}" if port is not None else hostname
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _bounded_message(message: str, limit: int = 1_000) -> str:
    if len(message) <= limit:
        return message
    return f"{message[:limit]}…"


def _request_metadata(request: object) -> dict[str, object]:
    if request is None:
        return {"method": "", "resource_type": "", "url": ""}
    method = getattr(request, "method", "")
    resource_type = getattr(request, "resource_type", "")
    return {
        "method": _bounded_label(method),
        "resource_type": _bounded_label(resource_type),
        "url": _safe_url(getattr(request, "url", None)),
    }


def _bounded_label(value: object, limit: int = 100) -> str:
    if not isinstance(value, str):
        return ""
    return value[:limit]


def _request_label(metadata: dict[str, object]) -> str:
    parts = [
        value
        for value in (
            metadata.get("method"),
            metadata.get("resource_type"),
        )
        if isinstance(value, str) and value
    ]
    parts.append("request")
    return " ".join(parts)
