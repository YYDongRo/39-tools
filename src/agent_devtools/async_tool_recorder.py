from __future__ import annotations

from asyncio import CancelledError
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from functools import wraps
from inspect import isawaitable, iscoroutinefunction
from pathlib import Path
from time import monotonic_ns
from types import TracebackType
from typing import Any, Generic, TypeVar, cast

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.events import ActionEventCollector
from agent_devtools.failure import FailureCategory, classify_exception
from agent_devtools.report import write_session_html
from agent_devtools.runtime import RuntimeContext, collect_runtime_context
from agent_devtools.run_state import _RunStateReporter
from agent_devtools.serialization import write_session_json
from agent_devtools.session import ActionSession
from agent_devtools.tool_recorder import (
    _call_arguments,
    _changed_paths,
    _json_state,
    _method_names,
    _normalize_events,
)
from agent_devtools.verification import VerificationResult


ToolT = TypeVar("ToolT")
ReturnT = TypeVar("ReturnT")
MaybeAwaitable = ReturnT | Awaitable[ReturnT]


class RecordedAsyncTools(Generic[ToolT]):
    def __init__(
        self,
        tools: ToolT,
        output_dir: str | Path,
        *,
        capture_screenshot: (
            Callable[[Path], object | Awaitable[object]] | None
        ) = None,
        observe_state: (
            Callable[
                [],
                dict[str, object] | Awaitable[dict[str, object]],
            ]
            | None
        ) = None,
        goal: str | None = None,
        task_verification: (
            Callable[
                [],
                VerificationResult | Awaitable[VerificationResult],
            ]
            | None
        ) = None,
        methods: Iterable[str] | None = None,
        event_collector: ActionEventCollector | None = None,
        run_context: RuntimeContext | None = None,
        run_state_path: str | Path | None = None,
    ) -> None:
        if observe_state is not None and not callable(observe_state):
            raise TypeError("observe_state must be callable or None")
        if capture_screenshot is not None and not callable(capture_screenshot):
            raise TypeError("capture_screenshot must be callable or None")
        if task_verification is not None and not callable(task_verification):
            raise TypeError("task_verification must be callable or None")
        if task_verification is not None and goal is None:
            raise ValueError("automatic task verification requires a goal")

        self._tools = tools
        self._proxy = _AsyncToolProxy(self)
        self._methods = _method_names(methods)
        self._capture_screenshot = capture_screenshot
        self._observe_state = observe_state
        self._task_verification = task_verification
        self._event_collector = event_collector
        self._wrappers: dict[str, Callable[..., Awaitable[object]]] = {}
        self._active_action = False
        self.output_dir = Path(output_dir)
        self.session = ActionSession(
            goal=goal,
            run_context=(
                run_context
                if run_context is not None
                else collect_runtime_context()
            ),
        )

        if self.output_dir.exists() and any(self.output_dir.iterdir()):
            raise FileExistsError(
                f"session output directory is not empty: {self.output_dir}"
            )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._run_state = (
            _RunStateReporter(
                run_state_path,
                self.output_dir,
                goal,
                started_at=datetime.now(UTC),
            )
            if run_state_path is not None
            else None
        )

    @property
    def report_path(self) -> Path:
        return self.output_dir / "report.html"

    @property
    def raw_tools(self) -> ToolT:
        return self._tools

    def assert_task_passed(self) -> None:
        verification = self.session.verification
        report_path = self.report_path.resolve()
        if verification is None:
            raise AssertionError(
                "Task was not verified. Configure a task expectation or "
                f"task verification callback. Report: {report_path}"
            )
        if not verification.passed:
            raise AssertionError(
                f"Task verification failed: {verification.failure_reason}. "
                f"Report: {report_path}"
            )

    async def __aenter__(self) -> ToolT:
        return cast(ToolT, self._proxy)

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self._persist()
            if (
                exception_type is None
                and self._task_verification is not None
                and self.session.verification is None
            ):
                await self.verify_task(self._task_verification)
        except BaseException as error:
            if self._run_state is not None:
                self._run_state.finish(self.session, exception=error)
            raise
        else:
            if self._run_state is not None:
                if exception_type is None:
                    self._run_state.finish(self.session)
                else:
                    self._run_state.finish(
                        self.session,
                        error_type=exception_type.__name__,
                    )

    async def verify_task(
        self,
        verification: Callable[
            [],
            VerificationResult | Awaitable[VerificationResult],
        ],
    ) -> VerificationResult:
        if self.session.goal is None:
            raise ValueError("task verification requires a session goal")

        result = await _resolve(verification())
        if not isinstance(result, VerificationResult):
            raise TypeError("verification must return a VerificationResult")
        self.session.verification = result
        self._persist()
        return result

    def _tool_attribute(self, name: str) -> object:
        attribute = getattr(self._tools, name)
        if name.startswith("_") or not callable(attribute):
            return attribute
        if self._methods is not None and name not in self._methods:
            return attribute
        if self._methods is None and not iscoroutinefunction(attribute):
            return attribute

        if name not in self._wrappers:
            self._wrappers[name] = self._wrap_method(name, attribute)
        return self._wrappers[name]

    def _wrap_method(
        self,
        name: str,
        method: Callable[..., MaybeAwaitable[ReturnT]],
    ) -> Callable[..., Awaitable[ReturnT]]:
        @wraps(method)
        async def recorded_method(
            *args: object,
            **kwargs: object,
        ) -> ReturnT:
            if self._active_action:
                raise RuntimeError(
                    "concurrent async tool actions are not supported"
                )

            self._active_action = True
            try:
                arguments = _call_arguments(method, args, kwargs)
                observations: dict[str, object] = {}
                event_collection_started = False
                if self._observe_state is not None:
                    await _store_state_observation(
                        observations,
                        "state_before",
                        self._observe_state,
                    )

                async def operation() -> ReturnT:
                    nonlocal event_collection_started
                    if self._event_collector is not None:
                        event_collection_started = (
                            await _start_event_collection(
                                observations,
                                self._event_collector,
                            )
                        )
                    return await _resolve(method(*args, **kwargs))

                async def finalize_observations() -> None:
                    if (
                        event_collection_started
                        and self._event_collector is not None
                    ):
                        await _finish_event_collection(
                            observations,
                            self._event_collector,
                        )
                    if self._observe_state is None:
                        return
                    await _store_state_observation(
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

                return await self._record(
                    name,
                    arguments,
                    operation,
                    observations,
                    finalize_observations,
                )
            finally:
                self._active_action = False

        return recorded_method

    async def _record(
        self,
        action_type: str,
        arguments: dict[str, object],
        operation: Callable[[], Awaitable[ReturnT]],
        observations: dict[str, object],
        finalize_observations: Callable[[], Awaitable[None]],
    ) -> ReturnT:
        screenshot_before: Path | None = None
        screenshot_after: Path | None = None
        if self._capture_screenshot is not None:
            action_dir = Path("actions") / (
                f"{self.session.action_count + 1:03d}"
            )
            (self.output_dir / action_dir).mkdir(
                parents=True,
                exist_ok=False,
            )
            screenshot_before = action_dir / "before.png"
            screenshot_after = action_dir / "after.png"
            await _resolve(
                self._capture_screenshot(
                    self.output_dir / screenshot_before
                )
            )

        start_time = datetime.now(UTC)
        start_ns = monotonic_ns()
        result: ReturnT | None = None
        operation_error: BaseException | None = None
        operation_traceback: TracebackType | None = None
        try:
            result = await operation()
        except (CancelledError, Exception) as error:
            operation_error = error
            operation_traceback = error.__traceback__

        duration_ms = (monotonic_ns() - start_ns) // 1_000_000
        lifecycle_error: BaseException | None = None
        lifecycle_traceback: TracebackType | None = None
        try:
            await finalize_observations()
        except CancelledError as error:
            lifecycle_error = error
            lifecycle_traceback = error.__traceback__
            observations["observation_finalizer_error_type"] = type(
                error
            ).__name__
        except Exception as error:
            observations["observation_finalizer_error_type"] = type(
                error
            ).__name__

        action = _action_from_result(
            action_type=action_type,
            arguments=arguments,
            start_time=start_time,
            duration_ms=duration_ms,
            screenshot_before=screenshot_before,
            screenshot_after=screenshot_after,
            observations=observations,
            operation_error=operation_error,
        )

        if self._capture_screenshot is not None and screenshot_after is not None:
            try:
                await _resolve(
                    self._capture_screenshot(
                        self.output_dir / screenshot_after
                    )
                )
            except CancelledError as error:
                action.screenshot_after = None
                self._append_and_persist(action)
                raise error.with_traceback(error.__traceback__)
            except Exception:
                action.screenshot_after = None
                self._append_and_persist(action)
                raise

        self._append_and_persist(action)
        if operation_error is not None:
            raise operation_error.with_traceback(operation_traceback)
        if lifecycle_error is not None:
            raise lifecycle_error.with_traceback(lifecycle_traceback)
        return cast(ReturnT, result)

    def _append_and_persist(self, action: ActionRecord) -> None:
        self.session.verification = None
        self.session.actions.append(action)
        self._persist()

    def _persist(self) -> None:
        write_session_json(self.session, self.output_dir / "session.json")
        write_session_html(self.session, self.output_dir / "report.html")
        if self._run_state is not None:
            self._run_state.update_action_count(self.session.action_count)


class _AsyncToolProxy:
    def __init__(self, recording: RecordedAsyncTools[Any]) -> None:
        self._recording = recording

    def __getattr__(self, name: str) -> object:
        return self._recording._tool_attribute(name)


def record_async_tools(
    tools: ToolT,
    output_dir: str | Path,
    *,
    capture_screenshot: (
        Callable[[Path], object | Awaitable[object]] | None
    ) = None,
    observe_state: (
        Callable[
            [],
            dict[str, object] | Awaitable[dict[str, object]],
        ]
        | None
    ) = None,
    goal: str | None = None,
    task_verification: (
        Callable[
            [],
            VerificationResult | Awaitable[VerificationResult],
        ]
        | None
    ) = None,
    methods: Iterable[str] | None = None,
    event_collector: ActionEventCollector | None = None,
    run_context: RuntimeContext | None = None,
    run_state_path: str | Path | None = None,
) -> RecordedAsyncTools[ToolT]:
    return RecordedAsyncTools(
        tools,
        output_dir,
        capture_screenshot=capture_screenshot,
        observe_state=observe_state,
        goal=goal,
        task_verification=task_verification,
        methods=methods,
        event_collector=event_collector,
        run_context=run_context,
        run_state_path=run_state_path,
    )


async def _resolve(value: MaybeAwaitable[ReturnT]) -> ReturnT:
    if isawaitable(value):
        return await value
    return value


async def _store_state_observation(
    observations: dict[str, object],
    key: str,
    observe_state: Callable[
        [],
        dict[str, object] | Awaitable[dict[str, object]],
    ],
) -> None:
    try:
        state = await _resolve(observe_state())
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


async def _start_event_collection(
    observations: dict[str, object],
    event_collector: ActionEventCollector,
) -> bool:
    try:
        await _resolve(event_collector.start())
    except Exception as error:
        observations["event_collection_start_error_type"] = type(
            error
        ).__name__
        return False
    return True


async def _finish_event_collection(
    observations: dict[str, object],
    event_collector: ActionEventCollector,
) -> None:
    try:
        events = await _resolve(event_collector.finish())
        normalized = _normalize_events(events)
    except Exception as error:
        observations["event_collection_finish_error_type"] = type(
            error
        ).__name__
        return
    if normalized:
        observations["browser_events"] = normalized


def _action_from_result(
    *,
    action_type: str,
    arguments: dict[str, object],
    start_time: datetime,
    duration_ms: int,
    screenshot_before: Path | None,
    screenshot_after: Path | None,
    observations: dict[str, object],
    operation_error: BaseException | None,
) -> ActionRecord:
    if operation_error is None:
        return ActionRecord(
            action_type=action_type,
            arguments=arguments,
            start_time=start_time,
            duration_ms=duration_ms,
            status=ActionStatus.SUCCESS,
            screenshot_before=screenshot_before,
            screenshot_after=screenshot_after,
            observations=dict(observations),
        )

    category = FailureCategory.OPERATION_ERROR
    if isinstance(operation_error, Exception):
        category = classify_exception(operation_error)
    return ActionRecord(
        action_type=action_type,
        arguments=arguments,
        start_time=start_time,
        duration_ms=duration_ms,
        status=ActionStatus.FAILURE,
        screenshot_before=screenshot_before,
        screenshot_after=screenshot_after,
        failure_reason=(
            f"{type(operation_error).__name__}: {operation_error}"
        ),
        failure_category=category,
        observations=dict(observations),
    )
