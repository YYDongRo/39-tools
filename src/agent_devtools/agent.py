from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from contextlib import contextmanager
from datetime import UTC, datetime
from inspect import isawaitable
from pathlib import Path
from typing import Generic, TypeVar
from uuid import uuid4

from agent_devtools.action import ActionStatus
from agent_devtools.async_tool_recorder import (
    RecordedAsyncTools,
    record_async_tools,
)
from agent_devtools.events import ActionEventCollector
from agent_devtools.failure import record_agent_run_failure
from agent_devtools.final_state import FinalStateObservation
from agent_devtools.report_opening import open_local_report
from agent_devtools.tool_recorder import RecordedTools, record_tools
from agent_devtools.trajectory import TrajectoryVerificationResult
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
SyncFinalStateVerifier = Callable[[FinalStateObservation], VerificationResult]
AsyncFinalStateVerifier = Callable[
    [FinalStateObservation], VerificationResult | Awaitable[VerificationResult]
]
SyncTrajectoryVerifier = Callable[
    [FinalStateObservation], TrajectoryVerificationResult
]
AsyncTrajectoryVerifier = Callable[
    [FinalStateObservation],
    TrajectoryVerificationResult | Awaitable[TrajectoryVerificationResult],
]


class ObservedAgent(Generic[AgentT, ToolT]):
    """Wrap an agent at its tool boundary.

    Agents can receive the recording proxy as ``run(..., tools=...)`` or bind
    it temporarily to an existing tool attribute with ``tools_attribute``.
    """

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
        final_state_verifier: SyncFinalStateVerifier | None = None,
        trajectory_verifier: SyncTrajectoryVerifier | None = None,
        methods: Iterable[str] | None = None,
        event_collector: ActionEventCollector | None = None,
        tools_attribute: str | None = None,
    ) -> None:
        _validate_agent(agent)
        _validate_optional_task(task)
        _validate_tools_attribute(tools_attribute)
        _validate_final_state_verifier(
            task_verification,
            final_state_verifier,
            trajectory_verifier,
        )
        self.agent = agent
        self.tools = tools
        self.output_root = Path(output_root)
        self.task = task
        self.capture_screenshot = capture_screenshot
        self.observe_state = observe_state
        self.task_verification = task_verification
        self.final_state_verifier = final_state_verifier
        self.trajectory_verifier = trajectory_verifier
        self.methods = methods
        self.event_collector = event_collector
        self.tools_attribute = tools_attribute
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
                    with _bind_tools(
                        self.agent,
                        self.tools_attribute,
                        recorded_tools,
                    ):
                        if self.tools_attribute is None:
                            result = self.agent.run(  # type: ignore[attr-defined]
                                task,
                                *args,
                                tools=recorded_tools,
                                **kwargs,
                            )
                        else:
                            result = self.agent.run(  # type: ignore[attr-defined]
                                task,
                                *args,
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
                    if self.final_state_verifier is not None:
                        _apply_final_state_verifier(
                            trace,
                            task,
                            self.observe_state,
                            self.final_state_verifier,
                        )
                    if self.trajectory_verifier is not None:
                        _apply_trajectory_verifier(
                            trace,
                            task,
                            self.observe_state,
                            self.trajectory_verifier,
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
        return open_local_report(self.last_report_path)


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
        final_state_verifier: AsyncFinalStateVerifier | None = None,
        trajectory_verifier: AsyncTrajectoryVerifier | None = None,
        methods: Iterable[str] | None = None,
        event_collector: ActionEventCollector | None = None,
        tools_attribute: str | None = None,
    ) -> None:
        _validate_agent(agent)
        _validate_optional_task(task)
        _validate_tools_attribute(tools_attribute)
        _validate_final_state_verifier(
            task_verification,
            final_state_verifier,
            trajectory_verifier,
        )
        self.agent = agent
        self.tools = tools
        self.output_root = Path(output_root)
        self.task = task
        self.capture_screenshot = capture_screenshot
        self.observe_state = observe_state
        self.task_verification = task_verification
        self.final_state_verifier = final_state_verifier
        self.trajectory_verifier = trajectory_verifier
        self.methods = methods
        self.event_collector = event_collector
        self.tools_attribute = tools_attribute
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
                    with _bind_tools(
                        self.agent,
                        self.tools_attribute,
                        recorded_tools,
                    ):
                        if self.tools_attribute is None:
                            result = self.agent.run(  # type: ignore[attr-defined]
                                task,
                                *args,
                                tools=recorded_tools,
                                **kwargs,
                            )
                        else:
                            result = self.agent.run(  # type: ignore[attr-defined]
                                task,
                                *args,
                                **kwargs,
                            )
                        if not isawaitable(result):
                            raise TypeError(
                                "observe_async_agent() requires an async agent "
                                "run method"
                            )
                        resolved_result = await result
                    if self.final_state_verifier is not None:
                        await _apply_async_final_state_verifier(
                            trace,
                            task,
                            self.observe_state,
                            self.final_state_verifier,
                        )
                    if self.trajectory_verifier is not None:
                        await _apply_async_trajectory_verifier(
                            trace,
                            task,
                            self.observe_state,
                            self.trajectory_verifier,
                        )
                    return resolved_result
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
        return open_local_report(self.last_report_path)


def observe_agent(
    agent: AgentT,
    tools: ToolT,
    output_root: str | Path,
    *,
    task: str | None = None,
    capture_screenshot: SyncScreenshot | None = None,
    observe_state: SyncStateObserver | None = None,
    task_verification: SyncTaskVerification | None = None,
    final_state_verifier: SyncFinalStateVerifier | None = None,
    trajectory_verifier: SyncTrajectoryVerifier | None = None,
    methods: Iterable[str] | None = None,
    event_collector: ActionEventCollector | None = None,
    tools_attribute: str | None = None,
) -> ObservedAgent[AgentT, ToolT]:
    return ObservedAgent(
        agent,
        tools,
        output_root,
        task=task,
        capture_screenshot=capture_screenshot,
        observe_state=observe_state,
        task_verification=task_verification,
        final_state_verifier=final_state_verifier,
        trajectory_verifier=trajectory_verifier,
        methods=methods,
        event_collector=event_collector,
        tools_attribute=tools_attribute,
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
    final_state_verifier: AsyncFinalStateVerifier | None = None,
    trajectory_verifier: AsyncTrajectoryVerifier | None = None,
    methods: Iterable[str] | None = None,
    event_collector: ActionEventCollector | None = None,
    tools_attribute: str | None = None,
) -> ObservedAsyncAgent[AgentT, ToolT]:
    return ObservedAsyncAgent(
        agent,
        tools,
        output_root,
        task=task,
        capture_screenshot=capture_screenshot,
        observe_state=observe_state,
        task_verification=task_verification,
        final_state_verifier=final_state_verifier,
        trajectory_verifier=trajectory_verifier,
        methods=methods,
        event_collector=event_collector,
        tools_attribute=tools_attribute,
    )


def _validate_agent(agent: object) -> None:
    if not callable(getattr(agent, "run", None)):
        raise TypeError("agent must provide a callable run method")


def _validate_tools_attribute(attribute: object) -> None:
    if attribute is not None and (
        not isinstance(attribute, str) or not attribute.strip()
    ):
        raise ValueError("tools_attribute must be a non-empty string or None")


@contextmanager
def _bind_tools(
    agent: object,
    attribute: str | None,
    recorded_tools: object,
):
    if attribute is None:
        yield
        return

    if not hasattr(agent, attribute):
        raise AttributeError(
            f"agent has no tools attribute {attribute!r}"
        )
    original_tools = getattr(agent, attribute)
    setattr(agent, attribute, recorded_tools)
    try:
        yield
    finally:
        setattr(agent, attribute, original_tools)


def _validate_optional_task(task: object) -> None:
    if task is not None and (
        not isinstance(task, str) or not task.strip()
    ):
        raise ValueError("task must be a non-empty string or None")


def _validate_final_state_verifier(
    task_verification: object,
    final_state_verifier: object,
    trajectory_verifier: object,
) -> None:
    configured = sum(
        value is not None
        for value in (
            task_verification,
            final_state_verifier,
            trajectory_verifier,
        )
    )
    if configured > 1:
        raise ValueError(
            "use either task_verification, final_state_verifier, or "
            "trajectory_verifier, not more than one"
        )
    if final_state_verifier is not None and not callable(final_state_verifier):
        raise TypeError("final_state_verifier must be callable or None")
    if trajectory_verifier is not None and not callable(trajectory_verifier):
        raise TypeError("trajectory_verifier must be callable or None")


def _build_final_state_observation(
    trace: RecordedTools[object] | RecordedAsyncTools[object],
    task: str,
    observe_state: Callable[[], object] | None,
) -> FinalStateObservation:
    state = observe_state() if observe_state is not None else {}
    if isawaitable(state):
        close = getattr(state, "close", None)
        if callable(close):
            close()
        raise TypeError(
            "async state observers require observe_async_agent()"
        )
    if not isinstance(state, dict):
        raise TypeError("observe_state must return a dictionary")

    screenshot_path: Path | None = None
    if trace.session.actions:
        relative_path = trace.session.actions[-1].screenshot_after
        if relative_path is not None:
            screenshot_path = (
                trace.report_path.parent / relative_path
            ).resolve()
    return FinalStateObservation(
        task=task,
        state=state,
        actions=tuple(trace.session.actions),
        screenshot_path=screenshot_path,
        trace_directory=trace.report_path.resolve().parent,
    )


def _store_final_state_verification(
    trace: RecordedTools[object] | RecordedAsyncTools[object],
    result: VerificationResult,
) -> None:
    trace.session.verification = result
    trace.session.verification_source = "generic:final-state"
    trace.session.verification_note = None


def _store_final_state_verification_error(
    trace: RecordedTools[object] | RecordedAsyncTools[object],
    error: Exception,
) -> None:
    trace.session.verification = None
    trace.session.verification_source = "generic:final-state"
    trace.session.verification_note = (
        "Final-state verification unavailable "
        f"({type(error).__name__})."
    )


def _apply_final_state_verifier(
    trace: RecordedTools[object],
    task: str,
    observe_state: SyncStateObserver | None,
    verifier: SyncFinalStateVerifier,
) -> None:
    try:
        observation = _build_final_state_observation(
            trace,
            task,
            observe_state,
        )
        result = verifier(observation)
        if isawaitable(result):
            close = getattr(result, "close", None)
            if callable(close):
                close()
            raise TypeError(
                "async final-state verifiers require "
                "observe_async_agent()"
            )
        if not isinstance(result, VerificationResult):
            raise TypeError(
                "final_state_verifier must return VerificationResult"
            )
    except Exception as error:
        _store_final_state_verification_error(trace, error)
        return
    _store_final_state_verification(trace, result)


async def _apply_async_final_state_verifier(
    trace: RecordedAsyncTools[object],
    task: str,
    observe_state: AsyncStateObserver | None,
    verifier: AsyncFinalStateVerifier,
) -> None:
    try:
        state = observe_state() if observe_state is not None else {}
        if isawaitable(state):
            state = await state
        if not isinstance(state, dict):
            raise TypeError("observe_state must return a dictionary")

        screenshot_path: Path | None = None
        if trace.session.actions:
            relative_path = trace.session.actions[-1].screenshot_after
            if relative_path is not None:
                screenshot_path = (
                    trace.report_path.parent / relative_path
                ).resolve()
        observation = FinalStateObservation(
            task=task,
            state=state,
            actions=tuple(trace.session.actions),
            screenshot_path=screenshot_path,
            trace_directory=trace.report_path.resolve().parent,
        )
        result = verifier(observation)
        if isawaitable(result):
            result = await result
        if not isinstance(result, VerificationResult):
            raise TypeError(
                "final_state_verifier must return VerificationResult"
            )
    except Exception as error:
        _store_final_state_verification_error(trace, error)
        return
    _store_final_state_verification(trace, result)


def _apply_trajectory_verifier(
    trace: RecordedTools[object],
    task: str,
    observe_state: SyncStateObserver | None,
    verifier: SyncTrajectoryVerifier,
) -> None:
    try:
        observation = _build_final_state_observation(
            trace,
            task,
            observe_state,
        )
        result = verifier(observation)
        if isawaitable(result):
            close = getattr(result, "close", None)
            if callable(close):
                close()
            raise TypeError(
                "async trajectory verifiers require "
                "observe_async_agent()"
            )
        if not isinstance(result, TrajectoryVerificationResult):
            raise TypeError(
                "trajectory_verifier must return "
                "TrajectoryVerificationResult"
            )
        _store_trajectory_verification(trace, result)
    except Exception as error:
        _store_trajectory_verification_error(trace, error)


async def _apply_async_trajectory_verifier(
    trace: RecordedAsyncTools[object],
    task: str,
    observe_state: AsyncStateObserver | None,
    verifier: AsyncTrajectoryVerifier,
) -> None:
    try:
        state = observe_state() if observe_state is not None else {}
        if isawaitable(state):
            state = await state
        if not isinstance(state, dict):
            raise TypeError("observe_state must return a dictionary")

        screenshot_path: Path | None = None
        if trace.session.actions:
            relative_path = trace.session.actions[-1].screenshot_after
            if relative_path is not None:
                screenshot_path = (
                    trace.report_path.parent / relative_path
                ).resolve()
        observation = FinalStateObservation(
            task=task,
            state=state,
            actions=tuple(trace.session.actions),
            screenshot_path=screenshot_path,
            trace_directory=trace.report_path.resolve().parent,
        )
        result = verifier(observation)
        if isawaitable(result):
            result = await result
        if not isinstance(result, TrajectoryVerificationResult):
            raise TypeError(
                "trajectory_verifier must return "
                "TrajectoryVerificationResult"
            )
        _store_trajectory_verification(trace, result)
    except Exception as error:
        _store_trajectory_verification_error(trace, error)


def _store_trajectory_verification(
    trace: RecordedTools[object] | RecordedAsyncTools[object],
    result: TrajectoryVerificationResult,
) -> None:
    actions = trace.session.actions
    if len(result.actions) != len(actions):
        raise ValueError(
            "trajectory_verifier must return one action result per recorded "
            "action"
        )

    notes = result.action_notes or (None,) * len(actions)
    for action, verification, note in zip(
        actions,
        result.actions,
        notes,
        strict=True,
    ):
        if action.status is ActionStatus.FAILURE:
            # Execution failure is authoritative; a model cannot turn it into
            # a successful action verification.
            continue
        action.verification = verification
        if note is not None:
            action.observations["verification_note"] = note

    trace.session.verification = result.final
    trace.session.verification_source = result.source
    trace.session.verification_note = result.note


def _store_trajectory_verification_error(
    trace: RecordedTools[object] | RecordedAsyncTools[object],
    error: Exception,
) -> None:
    trace.session.verification = None
    trace.session.verification_source = "generic:trajectory"
    trace.session.verification_note = (
        "Trajectory verification unavailable "
        f"({type(error).__name__})."
    )


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
    "FinalStateObservation",
    "ObservedAgent",
    "ObservedAsyncAgent",
    "TrajectoryVerificationResult",
    "observe_agent",
    "observe_async_agent",
]
