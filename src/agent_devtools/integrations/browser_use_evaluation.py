from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from inspect import isawaitable
from pathlib import Path
from time import monotonic_ns
from typing import TypeVar
from uuid import uuid4

from agent_devtools.evaluation import (
    AgentEvaluation,
    EvaluationRun,
    EvaluationRunStatus,
)
from agent_devtools.evaluation_comparison import compare_evaluations
from agent_devtools.evaluation_comparison_report import (
    write_evaluation_comparison_html,
)
from agent_devtools.evaluation_comparison_serialization import (
    write_evaluation_comparison_json,
)
from agent_devtools.evaluation_analysis import analyze_evaluation_runs
from agent_devtools.evaluation_report import write_evaluation_html
from agent_devtools.evaluation_serialization import (
    read_evaluation_json,
    write_evaluation_json,
)
from agent_devtools.config import AgentDevToolsConfig
from agent_devtools.diagnostics import classify_run_issue
from agent_devtools.integrations.browser_use import (
    BrowserUseFinalCheck,
    ObservedBrowserUseAgent,
)
from agent_devtools.report import write_session_html
from agent_devtools.serialization import write_session_json
from agent_devtools.session import ActionSession


AgentT = TypeVar("AgentT")


class _FreshAgentRequiredError(TypeError):
    pass


class _FixedTraceObservedAgent(ObservedBrowserUseAgent[AgentT]):
    def __init__(
        self,
        agent: AgentT,
        goal: str,
        trace_directory: Path,
        final_check: BrowserUseFinalCheck | None,
        config: AgentDevToolsConfig,
    ) -> None:
        self._trace_directory = trace_directory
        super().__init__(
            agent,
            goal,
            trace_directory.parent,
            print_summary=False,
            final_check=final_check,
            config=replace(
                config,
                open_report=False,
                terminal_summary=False,
            ),
        )

    def _create_trace_directory(self) -> Path:
        return self._trace_directory


async def evaluate_browser_use_agent(
    *,
    agent_factory: Callable[[str], AgentT],
    task: str,
    runs: int,
    max_steps: int = 100,
    output_root: str | Path | None = None,
    final_check: BrowserUseFinalCheck | None = None,
    config: AgentDevToolsConfig | str | Path | None = None,
) -> AgentEvaluation:
    _validate_inputs(agent_factory, task, runs, max_steps, final_check)
    config_settings = _resolve_config(config)
    if not config_settings.enabled:
        raise ValueError(
            "Browser Use evaluation requires Agent DevTools recording to be enabled"
        )
    root = _safe_output_root(
        output_root
        if output_root is not None
        else config_settings.evaluation_directory
    )
    previous_evaluation = (
        _find_previous_evaluation(root, task)
        if config_settings.compare_previous
        else None
    )
    evaluation_id, output_dir = _create_evaluation_directory(root)
    evaluation_started_at = datetime.now(UTC)
    evaluation_runs: list[EvaluationRun] = []
    sessions: dict[int, ActionSession] = {}
    seen_agents: list[object] = []

    for run_number in range(1, runs + 1):
        run, session = await _evaluate_attempt(
            agent_factory=agent_factory,
            task=task,
            max_steps=max_steps,
            run_number=run_number,
            output_dir=output_dir,
            seen_agents=seen_agents,
            final_check=final_check,
            config=config_settings,
        )
        evaluation_runs.append(run)
        sessions[run_number] = session

    analyzed_runs, representative, patterns = analyze_evaluation_runs(
        tuple(evaluation_runs),
        sessions,
    )
    evaluation = AgentEvaluation(
        evaluation_id=evaluation_id,
        task=task,
        started_at=evaluation_started_at,
        ended_at=datetime.now(UTC),
        requested_run_count=runs,
        runs=analyzed_runs,
        output_dir=output_dir,
        representative_success_run_number=representative,
        failure_patterns=patterns,
    )
    write_evaluation_json(evaluation, output_dir / "evaluation.json")
    comparison = None
    if previous_evaluation is not None:
        comparison = compare_evaluations(previous_evaluation, evaluation)
        write_evaluation_comparison_json(
            comparison,
            output_dir / "comparison.json",
        )
        write_evaluation_comparison_html(
            comparison,
            output_dir / "comparison.html",
            baseline_report_href=_relative_report_href(
                output_dir,
                previous_evaluation.report_path,
            ),
        )
    write_evaluation_html(
        evaluation,
        evaluation.report_path,
        comparison_report_path=(
            "comparison.html" if comparison is not None else None
        ),
    )
    if config_settings.open_report:
        try:
            evaluation.open_report()
        except Exception:
            # Opening a local browser is a convenience and must not change
            # the evaluation result, especially in headless CI environments.
            pass
    return evaluation


async def _evaluate_attempt(
    *,
    agent_factory: Callable[[str], AgentT],
    task: str,
    max_steps: int,
    run_number: int,
    output_dir: Path,
    seen_agents: list[object],
    final_check: BrowserUseFinalCheck | None,
    config: AgentDevToolsConfig,
) -> tuple[EvaluationRun, ActionSession]:
    relative_trace = Path("runs") / f"{run_number:03d}"
    trace_directory = output_dir / relative_trace
    started_at = datetime.now(UTC)
    start_ns = monotonic_ns()
    agent: object | None = None
    observer: _FixedTraceObservedAgent[object] | None = None
    error_phase: str | None = None
    error_type: str | None = None
    fatal_error: BaseException | None = None

    try:
        try:
            factory_result = agent_factory(task)
            agent = (
                await factory_result
                if isawaitable(factory_result)
                else factory_result
            )
            error_phase = "setup"
            if any(agent is existing for existing in seen_agents):
                raise _FreshAgentRequiredError(
                    "agent_factory must return a fresh Agent for every run"
                )
            seen_agents.append(agent)
            observer = _FixedTraceObservedAgent(
                agent,
                task,
                trace_directory,
                final_check,
                config,
            )
            error_phase = "run"
            await observer.run(max_steps=max_steps)
            error_phase = None
        except Exception as error:
            error_type = _safe_error_type(error)
            if error_phase is None:
                error_phase = "factory"
        except BaseException as error:
            fatal_error = error
    finally:
        if agent is not None:
            try:
                close = getattr(agent, "close", None)
                if not callable(close):
                    raise TypeError("Browser Use Agent must provide close()")
                close_result = close()
                if isawaitable(close_result):
                    await close_result
            except Exception as error:
                if error_type is None:
                    error_phase = "cleanup"
                    error_type = _safe_error_type(error)

    if fatal_error is not None:
        raise fatal_error

    session = observer.last_session if observer is not None else None
    if session is None:
        session = _placeholder_session(task, error_phase, error_type)
        _write_trace(session, trace_directory)
    elif error_type is not None:
        session.verification = None
        session.verification_source = "evaluation"
        session.verification_note = _error_note(error_phase, error_type)
        session.issue_code = None
        _write_trace(session, trace_directory)

    status = (
        EvaluationRunStatus.ERRORED
        if error_type is not None
        else _verification_status(
            session,
            require_recorded_actions=config.require_recorded_actions,
        )
    )
    run_issue = classify_run_issue(session)
    ended_at = datetime.now(UTC)
    run = EvaluationRun(
        run_number=run_number,
        status=status,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=max(0, (monotonic_ns() - start_ns) // 1_000_000),
        action_count=session.action_count,
        trace_directory=relative_trace,
        report_path=relative_trace / "report.html",
        error_phase=error_phase if status is EvaluationRunStatus.ERRORED else None,
        error_type=error_type if status is EvaluationRunStatus.ERRORED else None,
        issue_code=run_issue.code.value if run_issue is not None else None,
    )
    return run, session


def _verification_status(
    session: ActionSession,
    *,
    require_recorded_actions: bool = False,
) -> EvaluationRunStatus:
    if (
        require_recorded_actions
        and session.action_count == 0
        and (session.verification is None or session.verification.passed)
    ):
        return EvaluationRunStatus.UNVERIFIED
    if session.verification is None:
        return EvaluationRunStatus.UNVERIFIED
    return (
        EvaluationRunStatus.PASSED
        if session.verification.passed
        else EvaluationRunStatus.FAILED
    )


def _placeholder_session(
    task: str,
    error_phase: str | None,
    error_type: str | None,
) -> ActionSession:
    return ActionSession(
        goal=task,
        verification_source="evaluation",
        verification_note=_error_note(error_phase, error_type),
    )


def _error_note(error_phase: str | None, error_type: str | None) -> str:
    return (
        "The evaluation attempt ended during "
        f"{error_phase or 'setup'} ({error_type or 'Exception'})."
    )


def _write_trace(session: ActionSession, trace_directory: Path) -> None:
    trace_directory.mkdir(parents=True, exist_ok=True)
    write_session_json(session, trace_directory / "session.json")
    write_session_html(session, trace_directory / "report.html")


def _find_previous_evaluation(
    root: Path,
    task: str,
) -> AgentEvaluation | None:
    """Find the newest complete evaluation for the exact same task."""

    if not root.is_dir():
        return None
    resolved_root = root.resolve()
    matches: list[tuple[datetime, str, AgentEvaluation]] = []
    for candidate in root.iterdir():
        if not candidate.is_dir():
            continue
        resolved_candidate = candidate.resolve()
        if resolved_candidate.parent != resolved_root:
            continue
        evaluation_path = candidate / "evaluation.json"
        report_path = candidate / "report.html"
        if not evaluation_path.is_file() or not report_path.is_file():
            continue
        try:
            evaluation = read_evaluation_json(evaluation_path)
        except (OSError, ValueError):
            continue
        if evaluation.task == task:
            matches.append(
                (evaluation.ended_at, evaluation.evaluation_id, evaluation)
            )
    if not matches:
        return None
    return max(matches, key=lambda item: (item[0], item[1]))[2]


def _relative_report_href(
    current_output_dir: Path,
    previous_report_path: Path,
) -> str:
    relative = os.path.relpath(
        previous_report_path.resolve(),
        start=current_output_dir.resolve(),
    )
    return relative.replace(os.sep, "/")


def _resolve_config(
    config: AgentDevToolsConfig | str | Path | None,
) -> AgentDevToolsConfig:
    if config is None:
        return AgentDevToolsConfig()
    if isinstance(config, AgentDevToolsConfig):
        return config
    if isinstance(config, (str, Path)):
        return AgentDevToolsConfig.from_file(config)
    raise TypeError(
        "config must be an AgentDevToolsConfig, a TOML path, or None"
    )


def _validate_inputs(
    agent_factory: object,
    task: object,
    runs: object,
    max_steps: object,
    final_check: object,
) -> None:
    if not callable(agent_factory):
        raise TypeError("agent_factory must be callable")
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task cannot be empty")
    if final_check is not None and not callable(final_check):
        raise TypeError("final_check must be callable or None")
    for name, value in (("runs", runs), ("max_steps", max_steps)):
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
        ):
            raise ValueError(f"{name} must be a positive integer")


def _safe_output_root(value: str | Path) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError("output_root must be a path")
    root = Path(value)
    resolved = root.resolve()
    anchor = Path(resolved.anchor)
    if resolved == anchor or resolved == Path.home().resolve():
        raise ValueError("output_root must not be a filesystem root or home directory")
    if root.exists() and not root.is_dir():
        raise ValueError("output_root must be a directory")
    return root


def _create_evaluation_directory(root: Path) -> tuple[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    while True:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        evaluation_id = f"{timestamp}-{uuid4().hex[:8]}"
        output_dir = root / evaluation_id
        try:
            output_dir.mkdir()
        except FileExistsError:
            continue
        (output_dir / "runs").mkdir()
        return evaluation_id, output_dir


def _safe_error_type(error: BaseException) -> str:
    name = type(error).__name__
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,99}", name):
        return name
    return "Exception"


__all__ = ["evaluate_browser_use_agent"]
