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
from agent_devtools.integrations.playwright_final_state import (
    AsyncFinalStateVerifier,
    FinalStateAssessment,
    FinalStateVerifier,
    observe_final_async_playwright_state,
    observe_final_playwright_state,
)
from agent_devtools.integrations.playwright_task import validate_task_expectation
from agent_devtools.failure import record_agent_run_failure
from agent_devtools.tool_recorder import RecordedTools
from agent_devtools.verification import VerificationResult


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
        final_state_verifier: FinalStateVerifier | None = None,
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
        if final_state_verifier is not None and not callable(
            final_state_verifier
        ):
            raise TypeError("final_state_verifier must be callable or None")
        if (
            expectation_generator is not None
            and final_state_verifier is not None
        ):
            raise ValueError(
                "use either expectation_generator or final_state_verifier, "
                "not both"
            )
        self.agent = agent
        self.tools = tools
        self.page = page
        self.output_root = Path(output_root)
        self.expectation_generator = expectation_generator
        self.final_state_verifier = final_state_verifier
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
                try:
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
                except BaseException as error:
                    record_agent_run_failure(trace.session, error)
                    raise
                if self.final_state_verifier is not None:
                    assessment = _verify_final_state_safely(
                        self.final_state_verifier,
                        user_request,
                        self.page,
                    )
                    _store_final_state_assessment(trace.session, assessment)
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
        final_state_verifier: AsyncFinalStateVerifier | None = None,
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
        if final_state_verifier is not None and not callable(
            final_state_verifier
        ):
            raise TypeError("final_state_verifier must be callable or None")
        if (
            expectation_generator is not None
            and final_state_verifier is not None
        ):
            raise ValueError(
                "use either expectation_generator or final_state_verifier, "
                "not both"
            )
        self.agent = agent
        self.tools = tools
        self.page = page
        self.output_root = Path(output_root)
        self.expectation_generator = expectation_generator
        self.final_state_verifier = final_state_verifier
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
                try:
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
                    resolved = await result
                except BaseException as error:
                    record_agent_run_failure(trace.session, error)
                    raise
                if self.final_state_verifier is not None:
                    assessment = await _verify_final_state_safely_async(
                        self.final_state_verifier,
                        user_request,
                        self.page,
                    )
                    _store_final_state_assessment(trace.session, assessment)
                return resolved
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
    final_state_verifier: FinalStateVerifier | None = None,
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
        final_state_verifier=final_state_verifier,
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
    final_state_verifier: AsyncFinalStateVerifier | None = None,
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
        final_state_verifier=final_state_verifier,
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


def _verify_final_state_safely(
    verifier: FinalStateVerifier,
    user_request: str,
    page: object,
) -> FinalStateAssessment:
    try:
        final_state = observe_final_playwright_state(  # type: ignore[arg-type]
            page
        )
        result = verifier(user_request, final_state)
        if isawaitable(result):
            close = getattr(result, "close", None)
            if callable(close):
                close()
            raise TypeError(
                "async final-state verifiers require "
                "observe_async_playwright_agent()"
            )
        return _normalize_final_state_assessment(verifier, result)
    except Exception as error:
        return _unavailable_final_state_assessment(verifier, error)


async def _verify_final_state_safely_async(
    verifier: AsyncFinalStateVerifier,
    user_request: str,
    page: object,
) -> FinalStateAssessment:
    try:
        final_state = await observe_final_async_playwright_state(
            page  # type: ignore[arg-type]
        )
        result = verifier(user_request, final_state)
        resolved = await result if isawaitable(result) else result
        return _normalize_final_state_assessment(verifier, resolved)
    except Exception as error:
        return _unavailable_final_state_assessment(verifier, error)


def _normalize_final_state_assessment(
    verifier: object,
    result: FinalStateAssessment | VerificationResult | None,
) -> FinalStateAssessment:
    if isinstance(result, FinalStateAssessment):
        return result
    source = _verifier_source(verifier)
    if isinstance(result, VerificationResult):
        return FinalStateAssessment(
            verification=result,
            source=source,
        )
    if result is None:
        return FinalStateAssessment(
            verification=None,
            source=source,
            note="The final page did not provide enough evidence to verify the task.",
        )
    raise TypeError(
        "final_state_verifier must return FinalStateAssessment, "
        "VerificationResult, or None"
    )


def _unavailable_final_state_assessment(
    verifier: object,
    error: Exception,
) -> FinalStateAssessment:
    return FinalStateAssessment(
        verification=None,
        source=_verifier_source(verifier),
        note=(
            "AI final-state assessment was unavailable "
            f"({type(error).__name__}). Check provider setup and page access."
        ),
    )


def _verifier_source(verifier: object) -> str:
    declared_source = getattr(verifier, "source", None)
    if isinstance(declared_source, str) and declared_source.strip():
        return declared_source
    return f"custom:{type(verifier).__name__}:final-state"


def _store_final_state_assessment(
    session: object,
    assessment: FinalStateAssessment,
) -> None:
    session.verification = assessment.verification  # type: ignore[attr-defined]
    session.verification_source = assessment.source  # type: ignore[attr-defined]
    session.verification_note = assessment.note  # type: ignore[attr-defined]


__all__ = [
    "AsyncExpectationGenerator",
    "AsyncFinalStateVerifier",
    "ExpectationGenerator",
    "FinalStateVerifier",
    "ObservedAsyncPlaywrightAgent",
    "ObservedPlaywrightAgent",
    "observe_async_playwright_agent",
    "observe_playwright_agent",
]
