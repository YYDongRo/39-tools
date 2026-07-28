from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from inspect import isawaitable
from pathlib import Path
from typing import Generic, TypeVar
from uuid import uuid4

from agent_devtools.async_tool_recorder import RecordedAsyncTools
from agent_devtools.integrations.playwright import (
    record_async_playwright_tools,
    record_playwright_tools,
)
from agent_devtools.integrations.playwright_task import TaskExpectation
from agent_devtools.integrations.playwright_expectation_generation import (
    GeneratedTaskExpectation,
)
from agent_devtools.integrations.playwright_task import validate_task_expectation
from agent_devtools.tool_recorder import RecordedTools


AgentT = TypeVar("AgentT")
ToolT = TypeVar("ToolT")

ExpectationGenerator = Callable[
    [str], TaskExpectation | GeneratedTaskExpectation | None
]
AsyncExpectationGenerator = Callable[
    [str],
    TaskExpectation
    | GeneratedTaskExpectation
    | None
    | Awaitable[TaskExpectation | GeneratedTaskExpectation | None],
]


class ObservedPlaywrightAgent(Generic[AgentT, ToolT]):
    def __init__(
        self,
        agent: AgentT,
        tools: ToolT,
        page: object,
        output_root: str | Path,
        *,
        expectation_generator: ExpectationGenerator | None = None,
        methods: Iterable[str] | None = None,
        full_page_screenshots: bool = False,
        capture_browser_events: bool = True,
        event_settle_ms: int = 100,
        max_browser_events: int = 20,
    ) -> None:
        run_method = getattr(agent, "run", None)
        if not callable(run_method):
            raise TypeError("agent must provide a callable run method")
        if expectation_generator is not None and not callable(
            expectation_generator
        ):
            raise TypeError("expectation_generator must be callable or None")
        self.agent = agent
        self.tools = tools
        self.page = page
        self.output_root = Path(output_root)
        self.expectation_generator = expectation_generator
        self.methods = methods
        self.full_page_screenshots = full_page_screenshots
        self.capture_browser_events = capture_browser_events
        self.event_settle_ms = event_settle_ms
        self.max_browser_events = max_browser_events
        self.last_trace: RecordedTools[ToolT] | None = None
        self._active = False

    @property
    def last_report_path(self) -> Path | None:
        if self.last_trace is None:
            return None
        return self.last_trace.report_path

    def run(
        self,
        user_request: str,
        *args: object,
        **kwargs: object,
    ) -> object:
        _validate_user_request(user_request)
        if "tools" in kwargs:
            raise ValueError("the observed agent owns the tools argument")
        if self._active:
            raise RuntimeError("an observed agent run is already active")

        self._active = True
        try:
            generated_expectation = None
            if self.expectation_generator is not None:
                generated_expectation = _generate_expectation_safely(
                    self.expectation_generator,
                    user_request,
                )

            trace = record_playwright_tools(
                self.tools,
                self.page,  # type: ignore[arg-type]
                _new_trace_directory(self.output_root),
                goal=user_request,
                task_expectation=(
                    generated_expectation.expectation
                    if generated_expectation is not None
                    else None
                ),
                methods=self.methods,
                full_page_screenshots=self.full_page_screenshots,
                capture_browser_events=self.capture_browser_events,
                event_settle_ms=self.event_settle_ms,
                max_browser_events=self.max_browser_events,
            )
            _store_generation_metadata(trace.session, generated_expectation)
            self.last_trace = trace
            with trace as recorded_tools:
                result = self.agent.run(  # type: ignore[attr-defined]
                    user_request,
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
                        "observe_async_playwright_agent()"
                    )
                return result
        finally:
            self._active = False

    def assert_last_task_passed(self) -> None:
        if self.last_trace is None:
            raise RuntimeError("the observed agent has not run yet")
        self.last_trace.assert_task_passed()


class ObservedAsyncPlaywrightAgent(Generic[AgentT, ToolT]):
    def __init__(
        self,
        agent: AgentT,
        tools: ToolT,
        page: object,
        output_root: str | Path,
        *,
        expectation_generator: AsyncExpectationGenerator | None = None,
        methods: Iterable[str] | None = None,
        full_page_screenshots: bool = False,
        capture_browser_events: bool = True,
        event_settle_ms: int = 100,
        max_browser_events: int = 20,
    ) -> None:
        run_method = getattr(agent, "run", None)
        if not callable(run_method):
            raise TypeError("agent must provide a callable run method")
        if expectation_generator is not None and not callable(
            expectation_generator
        ):
            raise TypeError("expectation_generator must be callable or None")
        self.agent = agent
        self.tools = tools
        self.page = page
        self.output_root = Path(output_root)
        self.expectation_generator = expectation_generator
        self.methods = methods
        self.full_page_screenshots = full_page_screenshots
        self.capture_browser_events = capture_browser_events
        self.event_settle_ms = event_settle_ms
        self.max_browser_events = max_browser_events
        self.last_trace: RecordedAsyncTools[ToolT] | None = None
        self._active = False

    @property
    def last_report_path(self) -> Path | None:
        if self.last_trace is None:
            return None
        return self.last_trace.report_path

    async def run(
        self,
        user_request: str,
        *args: object,
        **kwargs: object,
    ) -> object:
        _validate_user_request(user_request)
        if "tools" in kwargs:
            raise ValueError("the observed agent owns the tools argument")
        if self._active:
            raise RuntimeError("an observed agent run is already active")

        self._active = True
        try:
            generated_expectation = None
            if self.expectation_generator is not None:
                generated_expectation = await _generate_expectation_safely_async(
                    self.expectation_generator,
                    user_request,
                )

            trace = record_async_playwright_tools(
                self.tools,
                self.page,  # type: ignore[arg-type]
                _new_trace_directory(self.output_root),
                goal=user_request,
                task_expectation=(
                    generated_expectation.expectation
                    if generated_expectation is not None
                    else None
                ),
                methods=self.methods,
                full_page_screenshots=self.full_page_screenshots,
                capture_browser_events=self.capture_browser_events,
                event_settle_ms=self.event_settle_ms,
                max_browser_events=self.max_browser_events,
            )
            _store_generation_metadata(trace.session, generated_expectation)
            self.last_trace = trace
            async with trace as recorded_tools:
                result = self.agent.run(  # type: ignore[attr-defined]
                    user_request,
                    *args,
                    tools=recorded_tools,
                    **kwargs,
                )
                if not isawaitable(result):
                    raise TypeError(
                        "observe_async_playwright_agent() requires an "
                        "async agent run method"
                    )
                return await result
        finally:
            self._active = False

    def assert_last_task_passed(self) -> None:
        if self.last_trace is None:
            raise RuntimeError("the observed agent has not run yet")
        self.last_trace.assert_task_passed()


def observe_playwright_agent(
    agent: AgentT,
    tools: ToolT,
    page: object,
    output_root: str | Path,
    *,
    expectation_generator: ExpectationGenerator | None = None,
    methods: Iterable[str] | None = None,
    full_page_screenshots: bool = False,
    capture_browser_events: bool = True,
    event_settle_ms: int = 100,
    max_browser_events: int = 20,
) -> ObservedPlaywrightAgent[AgentT, ToolT]:
    return ObservedPlaywrightAgent(
        agent,
        tools,
        page,
        output_root,
        expectation_generator=expectation_generator,
        methods=methods,
        full_page_screenshots=full_page_screenshots,
        capture_browser_events=capture_browser_events,
        event_settle_ms=event_settle_ms,
        max_browser_events=max_browser_events,
    )


def observe_async_playwright_agent(
    agent: AgentT,
    tools: ToolT,
    page: object,
    output_root: str | Path,
    *,
    expectation_generator: AsyncExpectationGenerator | None = None,
    methods: Iterable[str] | None = None,
    full_page_screenshots: bool = False,
    capture_browser_events: bool = True,
    event_settle_ms: int = 100,
    max_browser_events: int = 20,
) -> ObservedAsyncPlaywrightAgent[AgentT, ToolT]:
    return ObservedAsyncPlaywrightAgent(
        agent,
        tools,
        page,
        output_root,
        expectation_generator=expectation_generator,
        methods=methods,
        full_page_screenshots=full_page_screenshots,
        capture_browser_events=capture_browser_events,
        event_settle_ms=event_settle_ms,
        max_browser_events=max_browser_events,
    )


def _validate_user_request(user_request: object) -> None:
    if not isinstance(user_request, str) or not user_request.strip():
        raise ValueError("user_request cannot be empty")


def _new_trace_directory(output_root: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return output_root / f"{timestamp}-{uuid4().hex[:8]}"


def _generate_expectation_safely(
    generator: ExpectationGenerator,
    user_request: str,
) -> GeneratedTaskExpectation:
    try:
        generated = generator(user_request)
        if isawaitable(generated):
            close = getattr(generated, "close", None)
            if callable(close):
                close()
            raise TypeError(
                "async expectation generators require "
                "observe_async_playwright_agent()"
            )
        return _normalize_generated_expectation(generated)
    except Exception as error:
        return _unavailable_generation(generator, error)


async def _generate_expectation_safely_async(
    generator: AsyncExpectationGenerator,
    user_request: str,
) -> GeneratedTaskExpectation:
    try:
        generated = generator(user_request)
        resolved = await generated if isawaitable(generated) else generated
        return _normalize_generated_expectation(resolved)
    except Exception as error:
        return _unavailable_generation(generator, error)


def _normalize_generated_expectation(
    generated: TaskExpectation | GeneratedTaskExpectation | None,
) -> GeneratedTaskExpectation:
    if isinstance(generated, GeneratedTaskExpectation):
        return generated
    if generated is None:
        return GeneratedTaskExpectation(
            expectation=None,
            inferred_goal=None,
            source="custom",
            note="The expectation generator could not derive a reliable check.",
        )
    validate_task_expectation(generated)
    return GeneratedTaskExpectation(
        expectation=generated,
        inferred_goal=None,
        source="custom",
    )


def _unavailable_generation(
    generator: object,
    error: Exception,
) -> GeneratedTaskExpectation:
    declared_source = getattr(generator, "source", None)
    source = (
        declared_source
        if isinstance(declared_source, str) and declared_source.strip()
        else f"custom:{type(generator).__name__}"
    )
    return GeneratedTaskExpectation(
        expectation=None,
        inferred_goal=None,
        source=source,
        note=(
            "Automatic verification was unavailable "
            f"({type(error).__name__}). Check provider setup and credentials."
        ),
    )


def _store_generation_metadata(
    session: object,
    generated: GeneratedTaskExpectation | None,
) -> None:
    if generated is None:
        return
    session.inferred_goal = generated.inferred_goal  # type: ignore[attr-defined]
    session.verification_source = generated.source  # type: ignore[attr-defined]
    session.verification_note = generated.note  # type: ignore[attr-defined]


__all__ = [
    "AsyncExpectationGenerator",
    "ExpectationGenerator",
    "ObservedAsyncPlaywrightAgent",
    "ObservedPlaywrightAgent",
    "observe_async_playwright_agent",
    "observe_playwright_agent",
]
