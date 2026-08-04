from __future__ import annotations

import webbrowser
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from inspect import isawaitable
from pathlib import Path
from typing import Generic, TypeVar
from uuid import uuid4

from agent_devtools.async_tool_recorder import (
    RecordedAsyncTools,
    record_async_tools,
)
from agent_devtools.events import ActionEventCollector
from agent_devtools.failure import record_agent_run_failure
from agent_devtools.tool_recorder import RecordedTools, record_tools
from agent_devtools.verification import VerificationResult


AgentT = TypeVar("AgentT")
ToolT = TypeVar("ToolT")

SyncScreenshot = Callable[[Path], object]
SyncStateObserver = Callable[[], dict[str, object]]
SyncTaskVerification = Callable[[], VerificationResult]
AsyncScreenshot = Callable[[Path], object | Awaitable[object]]
AsyncStateObserver = Callable[
    [], dict[str, object] | Awaitable[dict[str, object]]
]
AsyncTaskVerification = Callable[
    [], VerificationResult | Awaitable[VerificationResult]
]


class ObservedAgent(Generic[AgentT, ToolT]):
    """Wrap an agent whose run method accepts ``task`` and ``tools``."""

    def __init__(
        self,
        agent: AgentT,
        tools: ToolT,
        output_root: str | Path,
        *,
        task: str | None = None,
        capture_screenshot: SyncScreenshot | None = None,
        observe_state: SyncStateObserver | None = None,
        task_verification: SyncTaskVerification | None = None,
        methods: Iterable[str] | None = None,
        event_collector: ActionEventCollector | None = None,
    ) -> None:
        _validate_agent(agent)
        _validate_optional_task(task)
        self.agent = agent
        self.tools = tools
        self.output_root = Path(output_root)
        self.task = task
        self.capture_screenshot = capture_screenshot
        self.observe_state = observe_state
        self.task_verification = task_verification
        self.methods = methods
        self.event_collector = event_collector
        self.last_trace: RecordedTools[ToolT] | None = None
        self._active = False

    @property
    def last_report_path(self) -> Path | None:
        if self.last_trace is None:
            return None
        return self.last_trace.report_path

    def run(
        self,
        user_request: str | None = None,
        *args: object,
        **kwargs: object,
    ) -> object:
        task = _resolve_task(self.agent, self.task, user_request)
        if "tools" in kwargs:
            raise ValueError("the observed agent owns the tools argument")
        if self._active:
            raise RuntimeError("an observed agent run is already active")

        self._active = True
        try:
            trace = record_tools(
                self.tools,
                _new_trace_directory(self.output_root),
                capture_screenshot=self.capture_screenshot,
                observe_state=self.observe_state,
                goal=task,
                task_verification=self.task_verification,
                methods=self.methods,
                event_collector=self.event_collector,
            )
            self.last_trace = trace
            with trace as recorded_tools:
                try:
                    result = self.agent.run(  # type: ignore[attr-defined]
                        task,
                        *args,
                        tools=recorded_tools,
                        **kwargs,
                    )
                    if isawaitable(result):
                        close = getattr(result, "close", None)
                        if callable(close):
                            close()
                        raise TypeError(
                            "async agent run methods require "
                            "observe_async_agent()"
                        )
                    return result
                except BaseException as error:
                    record_agent_run_failure(trace.session, error)
                    raise
        finally:
            self._active = False

    def assert_last_task_passed(self) -> None:
        if self.last_trace is None:
            raise RuntimeError("the observed agent has not run yet")
        self.last_trace.assert_task_passed()

    def open_last_report(self) -> Path:
        if self.last_report_path is None:
            raise RuntimeError("the observed agent has not run yet")
        absolute_path = self.last_report_path.resolve()
        if not webbrowser.open(absolute_path.as_uri(), new=2):
            raise RuntimeError(f"could not open report: {absolute_path}")
        return absolute_path


class ObservedAsyncAgent(Generic[AgentT, ToolT]):
    """Async counterpart to :class:`ObservedAgent`."""

    def __init__(
        self,
        agent: AgentT,
        tools: ToolT,
        output_root: str | Path,
        *,
        task: str | None = None,
        capture_screenshot: AsyncScreenshot | None = None,
        observe_state: AsyncStateObserver | None = None,
        task_verification: AsyncTaskVerification | None = None,
        methods: Iterable[str] | None = None,
        event_collector: ActionEventCollector | None = None,
    ) -> None:
        _validate_agent(agent)
        _validate_optional_task(task)
        self.agent = agent
        self.tools = tools
        self.output_root = Path(output_root)
        self.task = task
        self.capture_screenshot = capture_screenshot
        self.observe_state = observe_state
        self.task_verification = task_verification
        self.methods = methods
        self.event_collector = event_collector
        self.last_trace: RecordedAsyncTools[ToolT] | None = None
        self._active = False

    @property
    def last_report_path(self) -> Path | None:
        if self.last_trace is None:
            return None
        return self.last_trace.report_path

    async def run(
        self,
        user_request: str | None = None,
        *args: object,
        **kwargs: object,
    ) -> object:
        task = _resolve_task(self.agent, self.task, user_request)
        if "tools" in kwargs:
            raise ValueError("the observed agent owns the tools argument")
        if self._active:
            raise RuntimeError("an observed agent run is already active")

        self._active = True
        try:
            trace = record_async_tools(
                self.tools,
                _new_trace_directory(self.output_root),
                capture_screenshot=self.capture_screenshot,
                observe_state=self.observe_state,
                goal=task,
                task_verification=self.task_verification,
                methods=self.methods,
                event_collector=self.event_collector,
            )
            self.last_trace = trace
            async with trace as recorded_tools:
                try:
                    result = self.agent.run(  # type: ignore[attr-defined]
                        task,
                        *args,
                        tools=recorded_tools,
                        **kwargs,
                    )
                    if not isawaitable(result):
                        raise TypeError(
                            "observe_async_agent() requires an async agent "
                            "run method"
                        )
                    return await result
                except BaseException as error:
                    record_agent_run_failure(trace.session, error)
                    raise
        finally:
            self._active = False

    def assert_last_task_passed(self) -> None:
        if self.last_trace is None:
            raise RuntimeError("the observed agent has not run yet")
        self.last_trace.assert_task_passed()

    def open_last_report(self) -> Path:
        if self.last_report_path is None:
            raise RuntimeError("the observed agent has not run yet")
        absolute_path = self.last_report_path.resolve()
        if not webbrowser.open(absolute_path.as_uri(), new=2):
            raise RuntimeError(f"could not open report: {absolute_path}")
        return absolute_path


def observe_agent(
    agent: AgentT,
    tools: ToolT,
    output_root: str | Path,
    *,
    task: str | None = None,
    capture_screenshot: SyncScreenshot | None = None,
    observe_state: SyncStateObserver | None = None,
    task_verification: SyncTaskVerification | None = None,
    methods: Iterable[str] | None = None,
    event_collector: ActionEventCollector | None = None,
) -> ObservedAgent[AgentT, ToolT]:
    return ObservedAgent(
        agent,
        tools,
        output_root,
        task=task,
        capture_screenshot=capture_screenshot,
        observe_state=observe_state,
        task_verification=task_verification,
        methods=methods,
        event_collector=event_collector,
    )


def observe_async_agent(
    agent: AgentT,
    tools: ToolT,
    output_root: str | Path,
    *,
    task: str | None = None,
    capture_screenshot: AsyncScreenshot | None = None,
    observe_state: AsyncStateObserver | None = None,
    task_verification: AsyncTaskVerification | None = None,
    methods: Iterable[str] | None = None,
    event_collector: ActionEventCollector | None = None,
) -> ObservedAsyncAgent[AgentT, ToolT]:
    return ObservedAsyncAgent(
        agent,
        tools,
        output_root,
        task=task,
        capture_screenshot=capture_screenshot,
        observe_state=observe_state,
        task_verification=task_verification,
        methods=methods,
        event_collector=event_collector,
    )


def _validate_agent(agent: object) -> None:
    if not callable(getattr(agent, "run", None)):
        raise TypeError("agent must provide a callable run method")


def _validate_optional_task(task: object) -> None:
    if task is not None and (
        not isinstance(task, str) or not task.strip()
    ):
        raise ValueError("task must be a non-empty string or None")


def _resolve_task(
    agent: object,
    configured_task: str | None,
    user_request: object,
) -> str:
    if user_request is not None:
        task = user_request
    elif configured_task is not None:
        task = configured_task
    else:
        task = getattr(agent, "task", None)
    if not isinstance(task, str) or not task.strip():
        raise ValueError(
            "agent task is unavailable; pass task=... or provide agent.task"
        )
    return task.strip()


def _new_trace_directory(output_root: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return output_root / f"{timestamp}-{uuid4().hex[:8]}"


__all__ = [
    "ObservedAgent",
    "ObservedAsyncAgent",
    "observe_agent",
    "observe_async_agent",
]
