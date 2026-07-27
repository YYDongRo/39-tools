from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from functools import wraps
from inspect import signature
from pathlib import Path
from types import TracebackType
from typing import Any, Generic, TypeVar, cast

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
        goal: str | None = None,
        task_verification: Callable[[], VerificationResult] | None = None,
        methods: Iterable[str] | None = None,
    ) -> None:
        self._tools = tools
        self._proxy = _ToolProxy(self)
        self._methods = _method_names(methods)
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
            result: ReturnT | None = None
            caught_error: Exception | None = None
            caught_traceback: TracebackType | None = None

            def operation() -> None:
                nonlocal result, caught_error, caught_traceback
                try:
                    result = method(*args, **kwargs)
                except Exception as error:
                    caught_error = error
                    caught_traceback = error.__traceback__
                    raise

            self._recorder.record(name, arguments, operation)

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
    goal: str | None = None,
    task_verification: Callable[[], VerificationResult] | None = None,
    methods: Iterable[str] | None = None,
) -> RecordedTools[ToolT]:
    return RecordedTools(
        tools,
        output_dir,
        capture_screenshot=capture_screenshot,
        goal=goal,
        task_verification=task_verification,
        methods=methods,
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
