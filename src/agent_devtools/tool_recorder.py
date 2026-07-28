from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from functools import wraps
from inspect import isawaitable, iscoroutinefunction, signature
from pathlib import Path
from types import TracebackType
from typing import Any, Generic, TypeVar, cast

from agent_devtools.events import ActionEventCollector
from agent_devtools.session import ActionSession
from agent_devtools.session_recorder import SessionRecorder
from agent_devtools.verification import VerificationResult


ToolT = TypeVar("ToolT")
ReturnT = TypeVar("ReturnT")


class RecordedTools(Generic[ToolT]):
    def __init__(
        self,
        tools: ToolT,
        output_dir: str | Path,
        *,
        capture_screenshot: Callable[[Path], None] | None = None,
        observe_state: Callable[[], dict[str, object]] | None = None,
        goal: str | None = None,
        task_verification: Callable[[], VerificationResult] | None = None,
        methods: Iterable[str] | None = None,
        event_collector: ActionEventCollector | None = None,
    ) -> None:
        if observe_state is not None and not callable(observe_state):
            raise TypeError("observe_state must be callable or None")
        self._tools = tools
        self._proxy = _ToolProxy(self)
        self._methods = _method_names(methods)
        self._observe_state = observe_state
        self._event_collector = event_collector
        self._wrappers: dict[str, Callable[..., object]] = {}
        self._recorder = SessionRecorder(
            Path(output_dir),
            capture_screenshot,
            goal=goal,
            task_verification=task_verification,
        )

    @property
    def session(self) -> ActionSession:
        return self._recorder.session

    @property
    def report_path(self) -> Path:
        return self._recorder.output_dir / "report.html"

    @property
    def raw_tools(self) -> ToolT:
        return self._tools

    def __enter__(self) -> ToolT:
        self._recorder.__enter__()
        return cast(ToolT, self._proxy)

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._recorder.__exit__(exception_type, exception, traceback)

    def _tool_attribute(self, name: str) -> object:
        attribute = getattr(self._tools, name)
        if (
            name.startswith("_")
            or not callable(attribute)
            or self._methods is not None
            and name not in self._methods
        ):
            return attribute

        if iscoroutinefunction(attribute):
            raise TypeError(
                f"async tool method {name!r} requires record_async_tools()"
            )

        if name not in self._wrappers:
            self._wrappers[name] = self._wrap_method(name, attribute)
        return self._wrappers[name]

    def _wrap_method(
        self,
        name: str,
        method: Callable[..., ReturnT],
    ) -> Callable[..., ReturnT]:
        @wraps(method)
        def recorded_method(*args: object, **kwargs: object) -> ReturnT:
            arguments = _call_arguments(method, args, kwargs)
            observations: dict[str, object] = {}
            if self._observe_state is not None:
                _store_state_observation(
                    observations,
                    "state_before",
                    self._observe_state,
                )
            result: ReturnT | None = None
            caught_error: Exception | None = None
            caught_traceback: TracebackType | None = None
            event_collection_started = False

            def operation() -> None:
                nonlocal event_collection_started
                nonlocal result, caught_error, caught_traceback
                if self._event_collector is not None:
                    event_collection_started = _start_event_collection(
                        observations,
                        self._event_collector,
                    )
                try:
                    result = method(*args, **kwargs)
                    if isawaitable(result):
                        close = getattr(result, "close", None)
                        if callable(close):
                            close()
                        raise TypeError(
                            f"async tool method {name!r} requires "
                            "record_async_tools()"
                        )
                except Exception as error:
                    caught_error = error
                    caught_traceback = error.__traceback__
                    raise

            def finalize_observations() -> None:
                if (
                    event_collection_started
                    and self._event_collector is not None
                ):
                    _finish_event_collection(
                        observations,
                        self._event_collector,
                    )
                if self._observe_state is None:
                    return
                _store_state_observation(
                    observations,
                    "state_after",
                    self._observe_state,
                )
                state_before = observations.get("state_before")
                state_after = observations.get("state_after")
                if isinstance(state_before, dict) and isinstance(
                    state_after,
                    dict,
                ):
                    observations["state_changes"] = _changed_paths(
                        state_before,
                        state_after,
                    )

            self._recorder.record(
                name,
                arguments,
                operation,
                observations=observations,
                finalize_observations=finalize_observations,
            )

            if caught_error is not None:
                raise caught_error.with_traceback(caught_traceback)
            return cast(ReturnT, result)

        return recorded_method


class _ToolProxy:
    def __init__(self, recording: RecordedTools[Any]) -> None:
        self._recording = recording

    def __getattr__(self, name: str) -> object:
        return self._recording._tool_attribute(name)


def record_tools(
    tools: ToolT,
    output_dir: str | Path,
    *,
    capture_screenshot: Callable[[Path], None] | None = None,
    observe_state: Callable[[], dict[str, object]] | None = None,
    goal: str | None = None,
    task_verification: Callable[[], VerificationResult] | None = None,
    methods: Iterable[str] | None = None,
    event_collector: ActionEventCollector | None = None,
) -> RecordedTools[ToolT]:
    return RecordedTools(
        tools,
        output_dir,
        capture_screenshot=capture_screenshot,
        observe_state=observe_state,
        goal=goal,
        task_verification=task_verification,
        methods=methods,
        event_collector=event_collector,
    )


def _method_names(methods: Iterable[str] | None) -> frozenset[str] | None:
    if methods is None:
        return None
    if isinstance(methods, str):
        raise ValueError("methods must be an iterable of method names")

    names = frozenset(methods)
    if not all(isinstance(name, str) and name.strip() for name in names):
        raise ValueError("methods must contain non-empty strings")
    return names


def _call_arguments(
    method: Callable[..., object],
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> dict[str, object]:
    try:
        bound_arguments = signature(method).bind(*args, **kwargs).arguments
    except (TypeError, ValueError):
        return {
            "args": _json_value(args),
            "kwargs": _json_value(kwargs),
        }

    return {
        name: _json_value(value)
        for name, value in bound_arguments.items()
    }


def _json_value(value: object) -> Any:
    try:
        return json.loads(
            json.dumps(value, ensure_ascii=False, default=repr)
        )
    except (TypeError, ValueError, RecursionError):
        return repr(value)


def _store_state_observation(
    observations: dict[str, object],
    key: str,
    observe_state: Callable[[], dict[str, object]],
) -> None:
    try:
        state = observe_state()
        if not isinstance(state, dict) or not all(
            isinstance(name, str) for name in state
        ):
            raise TypeError(
                "observe_state must return a dictionary with string keys"
            )
        normalized_state = _json_state(state)
    except Exception as error:
        observations[f"{key}_error_type"] = type(error).__name__
        return

    observations[key] = normalized_state


def _start_event_collection(
    observations: dict[str, object],
    event_collector: ActionEventCollector,
) -> bool:
    try:
        result = event_collector.start()
        if isawaitable(result):
            close = getattr(result, "close", None)
            if callable(close):
                close()
            raise TypeError(
                "async event collectors require record_async_tools()"
            )
    except Exception as error:
        observations["event_collection_start_error_type"] = type(
            error
        ).__name__
        return False
    return True


def _finish_event_collection(
    observations: dict[str, object],
    event_collector: ActionEventCollector,
) -> None:
    try:
        events = event_collector.finish()
        if isawaitable(events):
            close = getattr(events, "close", None)
            if callable(close):
                close()
            raise TypeError(
                "async event collectors require record_async_tools()"
            )
        normalized = _normalize_events(events)
    except Exception as error:
        observations["event_collection_finish_error_type"] = type(
            error
        ).__name__
        return
    if normalized:
        observations["browser_events"] = normalized


def _normalize_events(events: object) -> list[dict[str, object]]:
    if not isinstance(events, list) or not all(
        isinstance(event, dict) for event in events
    ):
        raise TypeError("event collector must return a list of dictionaries")
    normalized = _json_state({"events": events})["events"]
    if not isinstance(normalized, list) or not all(
        isinstance(event, dict) for event in normalized
    ):
        raise TypeError("events must normalize to a list of dictionaries")
    return normalized


def _json_state(state: dict[str, object]) -> dict[str, object]:
    try:
        _validate_state_value(state)
        normalized = json.loads(
            json.dumps(state, ensure_ascii=False, allow_nan=False)
        )
    except (TypeError, ValueError, RecursionError) as error:
        raise TypeError("state must contain JSON-safe values") from error
    if not isinstance(normalized, dict):
        raise TypeError("state must normalize to a dictionary")
    return normalized


def _validate_state_value(value: object) -> None:
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("state dictionaries require string keys")
        for nested_value in value.values():
            _validate_state_value(nested_value)
        return
    if isinstance(value, (list, tuple)):
        for nested_value in value:
            _validate_state_value(nested_value)
        return
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    raise TypeError("state contains an unsupported value")


def _changed_paths(
    before: dict[str, object],
    after: dict[str, object],
    prefix: str = "",
) -> list[str]:
    changed: list[str] = []
    missing = object()
    for key in sorted(before.keys() | after.keys()):
        path = f"{prefix}.{key}" if prefix else key
        before_value = before.get(key, missing)
        after_value = after.get(key, missing)
        if isinstance(before_value, dict) and isinstance(after_value, dict):
            nested_changes = _changed_paths(
                before_value,
                after_value,
                path,
            )
            if len(nested_changes) == 1:
                changed.extend(nested_changes)
            elif nested_changes:
                changed.append(path)
        elif before_value != after_value:
            changed.append(path)
    return changed
