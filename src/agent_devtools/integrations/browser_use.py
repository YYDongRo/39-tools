from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from inspect import isawaitable
from pathlib import Path
from time import monotonic_ns
from typing import Awaitable, Generic, TypeAlias, TypeVar
from urllib.parse import urlsplit
from uuid import uuid4

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.config import AgentDevToolsConfig
from agent_devtools.diagnostics import RunIssueCode
from agent_devtools.failure import FailureCategory, record_agent_run_failure
from agent_devtools.report import format_session_summary, write_session_html
from agent_devtools.report_opening import open_local_report
from agent_devtools.runtime import collect_runtime_context
from agent_devtools.run_state import _RunStateReporter
from agent_devtools.serialization import write_session_json
from agent_devtools.session import ActionSession
from agent_devtools.verification import VerificationResult


AgentT = TypeVar("AgentT")
BrowserUseFinalCheck: TypeAlias = Callable[
    [dict[str, object]],
    VerificationResult | Awaitable[VerificationResult],
]

_READ_ONLY_ACTIONS = {
    "done",
    "dropdown_options",
    "extract",
    "extract_structured_data",
    "find_elements",
    "find_text",
    "read_file",
    "read_state",
    "save_as_pdf",
    "screenshot",
    "search_page",
    "wait",
}
_AUXILIARY_ACTIONS = {
    "append_file",
    "copy_file",
    "create_folder",
    "delete_file",
    "move_file",
    "replace_file",
    "write_file",
}


@dataclass(frozen=True)
class BrowserUseFinalStateCheck:
    """Check bounded final browser state without requiring an LLM."""

    url_contains: str | None = None
    title_contains: str | None = None

    def __post_init__(self) -> None:
        if self.url_contains is None and self.title_contains is None:
            raise ValueError(
                "at least one of url_contains or title_contains is required"
            )
        for field_name, value in (
            ("url_contains", self.url_contains),
            ("title_contains", self.title_contains),
        ):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} cannot be empty")

    def __call__(self, state: dict[str, object]) -> VerificationResult:
        url = state.get("url")
        title = state.get("title")
        checks: list[dict[str, object]] = []

        if self.url_contains is not None:
            url_value = url if isinstance(url, str) else "<missing>"
            passed = self.url_contains in url_value
            checks.append(
                {
                    "name": "url_contains",
                    "passed": passed,
                    "expected_state": f"URL contains {self.url_contains!r}",
                    "observed_state": f"URL is {url_value!r}",
                }
            )

        if self.title_contains is not None:
            title_value = title if isinstance(title, str) else "<missing>"
            passed = self.title_contains in title_value
            checks.append(
                {
                    "name": "title_contains",
                    "passed": passed,
                    "expected_state": (
                        f"title contains {self.title_contains!r}"
                    ),
                    "observed_state": f"title is {title_value!r}",
                }
            )

        passed = all(check["passed"] is True for check in checks)
        failed_checks = [
            str(check["expected_state"])
            for check in checks
            if check["passed"] is not True
        ]
        return VerificationResult(
            expected_state="all configured final browser checks pass",
            observed_state=(
                "all configured final browser checks pass"
                if passed
                else "; ".join(
                    str(check["observed_state"]) for check in checks
                )
            ),
            passed=passed,
            failure_reason=(
                None
                if passed
                else "Final browser state did not satisfy: "
                + "; ".join(failed_checks)
            ),
            evidence={
                "verification_type": "browser-use-final-state",
                "state": dict(state),
                "checks": checks,
            },
        )


@dataclass(frozen=True)
class BrowserUsePreflightCheck:
    """One local setup check performed before a Browser Use run."""

    name: str
    passed: bool
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("preflight check name cannot be empty")
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise ValueError("preflight check detail cannot be empty")


@dataclass(frozen=True)
class BrowserUsePreflightResult:
    """Local Browser Use setup checks; no model call or browser run occurs."""

    checks: tuple[BrowserUsePreflightCheck, ...]

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)


@dataclass
class _PendingAction:
    action_type: str
    arguments: dict[str, object]
    start_time: datetime
    start_ns: int
    screenshot_before: Path | None
    state_before: dict[str, object]


class _BrowserUseRecorder:
    def __init__(
        self,
        output_dir: Path,
        goal: str,
        *,
        capture_screenshots: bool = True,
        redact_sensitive_data: bool = True,
        run_state_path: str | Path | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=False)
        self.session = ActionSession(
            goal=goal,
            run_context=collect_runtime_context(),
        )
        self.capture_screenshots = capture_screenshots
        self.redact_sensitive_data = redact_sensitive_data
        self._pending: _PendingAction | None = None
        self._pending_auxiliary_index: int | None = None
        self._browser_session: object | None = None
        self._last_state: dict[str, object] | None = None
        self._run_state = _RunStateReporter(
            run_state_path,
            self.output_dir,
            goal,
            started_at=datetime.now(UTC),
        )
        self._persist()

    @property
    def report_path(self) -> Path:
        return self.output_dir / "report.html"

    def attach_browser_session(self, browser_session: object) -> None:
        get_state = getattr(browser_session, "get_browser_state_summary", None)
        if not callable(get_state):
            raise TypeError(
                "Browser Use agent must provide a browser session with "
                "get_browser_state_summary()"
            )
        self._browser_session = browser_session

    async def on_model_action(
        self,
        browser_state: object,
        model_output: object,
        step_number: int,
    ) -> None:
        if self._pending is not None:
            raise RuntimeError("Browser Use actions must not overlap")

        action_type, arguments = _action_from_model_output(
            model_output,
            redact_sensitive_data=self.redact_sensitive_data,
        )
        self._last_state = _page_state(
            browser_state,
            redact_sensitive_data=self.redact_sensitive_data,
        )
        if action_type in _AUXILIARY_ACTIONS:
            self.session.auxiliary_events.append(
                {
                    "event_type": "agent_auxiliary",
                    "action_type": action_type,
                    "arguments": arguments,
                    "browser_use_step": step_number,
                }
            )
            self._pending_auxiliary_index = (
                len(self.session.auxiliary_events) - 1
            )
            self._persist()
            return
        if action_type in _READ_ONLY_ACTIONS:
            return

        action_dir = Path("actions") / f"{self.session.action_count + 1:03d}"
        screenshot_before = None
        if self.capture_screenshots:
            screenshot_before = _save_screenshot(
                self.output_dir,
                action_dir / "before.png",
                await self._capture_screenshot(browser_state),
            )
        arguments["browser_use_step"] = step_number
        self._pending = _PendingAction(
            action_type=action_type,
            arguments=arguments,
            start_time=datetime.now(UTC),
            start_ns=monotonic_ns(),
            screenshot_before=screenshot_before,
            state_before=_page_state(
                browser_state,
                redact_sensitive_data=self.redact_sensitive_data,
            ),
        )

    async def on_step_end(self, agent: object) -> None:
        pending = self._pending
        self._pending = None
        auxiliary_index = self._pending_auxiliary_index
        self._pending_auxiliary_index = None
        state_after: dict[str, object] = {}
        screenshot_after: Path | None = None
        observation_error: str | None = None
        try:
            browser_session = getattr(agent, "browser_session")
            browser_state = await browser_session.get_browser_state_summary()
            state_after = _page_state(
                browser_state,
                redact_sensitive_data=self.redact_sensitive_data,
            )
            self._last_state = dict(state_after)
            if pending is None:
                self._finish_auxiliary_event(auxiliary_index, agent)
                self._persist()
                return
            action_dir = Path("actions") / f"{self.session.action_count + 1:03d}"
            if self.capture_screenshots:
                screenshot_after = _save_screenshot(
                    self.output_dir,
                    action_dir / "after.png",
                    await self._capture_screenshot(browser_state),
                )
        except Exception as error:
            observation_error = type(error).__name__
            if pending is None:
                self._finish_auxiliary_event(auxiliary_index, agent)
                self._persist()
                return

        duration_ms = max(0, (monotonic_ns() - pending.start_ns) // 1_000_000)

        errors, reported_failure = _latest_action_result(
            agent,
            redact_sensitive_data=self.redact_sensitive_data,
        )
        self._finish_auxiliary_event(
            auxiliary_index,
            agent,
            errors=errors,
            reported_failure=reported_failure,
        )
        failed = bool(errors) or reported_failure
        failure_reason = None
        failure_evidence: dict[str, object] = {}
        if failed:
            failure_reason = (
                errors[0]
                if errors
                else "Browser Use reported an unsuccessful action."
            )
            failure_evidence = {"browser_use_errors": errors[:3]}

        observations: dict[str, object] = {
            "adapter": "browser-use",
            "duration_scope": "post-decision Browser Use step",
            "state_before": pending.state_before,
            "state_after": state_after,
        }
        if observation_error is not None:
            observations["state_after_error_type"] = observation_error

        action_verification = (
            None
            if failed
            else _navigate_verification(
                pending.action_type,
                pending.arguments,
                state_after,
            )
        )

        action = ActionRecord(
            action_type=pending.action_type,
            arguments=pending.arguments,
            start_time=pending.start_time,
            duration_ms=duration_ms,
            status=ActionStatus.FAILURE if failed else ActionStatus.SUCCESS,
            screenshot_before=pending.screenshot_before,
            screenshot_after=screenshot_after,
            failure_reason=failure_reason,
            failure_category=(
                _failure_category(failure_reason) if failed else None
            ),
            failure_evidence=failure_evidence,
            observations=observations,
            verification=action_verification,
        )
        self.session.actions.append(action)
        self.session.verification = None
        self._persist()

    def _finish_auxiliary_event(
        self,
        index: int | None,
        agent: object,
        *,
        errors: list[str] | None = None,
        reported_failure: bool = False,
    ) -> None:
        if index is None or not (0 <= index < len(self.session.auxiliary_events)):
            return
        if errors is None:
            errors, reported_failure = _latest_action_result(
                agent,
                redact_sensitive_data=self.redact_sensitive_data,
            )
        event = self.session.auxiliary_events[index]
        event["status"] = "failure" if errors or reported_failure else "success"
        if errors:
            event["failure_reason"] = errors[0]

    async def final_state(self) -> dict[str, object]:
        if self._browser_session is None:
            raise RuntimeError("Browser Use browser session is not attached")
        try:
            browser_state = await self._browser_session.get_browser_state_summary()
            state = _page_state(
                browser_state,
                redact_sensitive_data=self.redact_sensitive_data,
            )
            self._last_state = dict(state)
            return state
        except Exception:
            if self._last_state is not None:
                return dict(self._last_state)
            raise

    def finish(
        self,
        history: object | None,
        *,
        run_error: BaseException | None = None,
        deterministic_verification: VerificationResult | None = None,
        deterministic_error_type: str | None = None,
    ) -> None:
        if run_error is not None:
            self.session.issue_code = None
            record_agent_run_failure(
                self.session,
                run_error,
                runtime_name="Browser Use agent",
            )
            self._persist()
            self._run_state.finish(self.session, exception=run_error)
            return

        if deterministic_error_type is not None:
            self.session.issue_code = None
            self.session.verification_source = "browser-use:deterministic"
            self.session.verification_note = (
                "Deterministic final checks could not run "
                f"({deterministic_error_type})."
            )
            self.session.verification = None
            self._persist()
            self._run_state.finish(
                self.session,
                error_type=deterministic_error_type,
                issue_code="final_check_error",
            )
            return

        judgement = _judgement(
            history,
            redact_sensitive_data=self.redact_sensitive_data,
        )
        judge_verification = _judge_verification(
            self.session.goal,
            judgement,
        )
        if deterministic_verification is not None:
            evidence = _json_safe(
                dict(deterministic_verification.evidence),
                redact_sensitive_data=self.redact_sensitive_data,
            )
            if not isinstance(evidence, dict):
                evidence = {}
            if judge_verification is not None:
                evidence["browser_use_judge"] = {
                    "passed": judge_verification.passed,
                    "observed_state": judge_verification.observed_state,
                    "failure_reason": judge_verification.failure_reason,
                }
            self.session.verification_source = "browser-use:deterministic"
            self.session.verification_note = None
            self.session.issue_code = None
            self.session.verification = VerificationResult(
                expected_state=deterministic_verification.expected_state,
                observed_state=deterministic_verification.observed_state,
                passed=deterministic_verification.passed,
                evidence=evidence,
                failure_reason=deterministic_verification.failure_reason,
                failure_category=deterministic_verification.failure_category,
            )
            self._persist()
            self._run_state.finish(self.session)
            return

        if judgement is None:
            issue_code = _history_failure_issue_code(history)
            self.session.verification_source = "browser-use"
            self.session.verification_note = (
                _history_failure_note(history)
                or "Browser Use did not return a final task judgment."
            )
            self.session.issue_code = (
                issue_code.value if issue_code is not None else None
            )
            self._persist()
            self._run_state.finish(self.session)
            return

        if judge_verification is None:
            self.session.verification_source = "browser-use:judge"
            self.session.verification_note = (
                "Browser Use returned an invalid final task judgment."
            )
            self.session.issue_code = None
            self._persist()
            self._run_state.finish(self.session)
            return
        self.session.verification_source = "browser-use:judge"
        self.session.verification_note = None
        self.session.issue_code = None
        self.session.verification = judge_verification
        self._persist()
        self._run_state.finish(self.session)

    async def _capture_screenshot(self, browser_state: object) -> object:
        encoded = getattr(browser_state, "screenshot", None)
        if isinstance(encoded, str) and encoded.strip():
            return encoded
        if self._browser_session is None:
            return None

        try:
            from browser_use.browser.events import ScreenshotEvent

            event_bus = getattr(self._browser_session, "event_bus")
            screenshot_event = event_bus.dispatch(
                ScreenshotEvent(full_page=False)
            )
            await screenshot_event
            return await screenshot_event.event_result(
                raise_if_any=True,
                raise_if_none=True,
            )
        except Exception:
            return None

    def _persist(self) -> None:
        write_session_json(self.session, self.output_dir / "session.json")
        write_session_html(self.session, self.report_path)
        self._run_state.update_action_count(
            self.session.action_count,
            self.session.actions[-1].action_type
            if self.session.actions
            else None,
        )


class ObservedBrowserUseAgent(Generic[AgentT]):
    def __init__(
        self,
        agent: AgentT,
        goal: str | None = None,
        output_root: str | Path | None = None,
        *,
        print_summary: bool | None = None,
        final_check: BrowserUseFinalCheck | None = None,
        config: AgentDevToolsConfig | str | Path | None = None,
    ) -> None:
        config_settings = _resolve_config(config)
        goal = _resolve_agent_goal(agent, goal)
        if config_settings.redact_sensitive_data:
            goal = _redact_text(goal)
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("goal cannot be empty")
        if not callable(getattr(agent, "run", None)):
            raise TypeError("agent must provide a callable async run method")
        if print_summary is None:
            print_summary = config_settings.terminal_summary
        if not isinstance(print_summary, bool):
            raise TypeError("print_summary must be a bool")
        if final_check is not None and not callable(final_check):
            raise TypeError("final_check must be callable or None")
        if not hasattr(agent, "register_new_step_callback"):
            raise TypeError("agent must be a compatible Browser Use Agent")
        if not hasattr(agent, "directly_open_url"):
            raise TypeError("agent must be a compatible Browser Use Agent")
        agent_settings = getattr(agent, "settings", None)
        if agent_settings is None or not hasattr(
            agent_settings,
            "max_actions_per_step",
        ):
            raise TypeError("agent must be a compatible Browser Use Agent")
        browser_session = getattr(agent, "browser_session", None)
        if not callable(
            getattr(browser_session, "get_browser_state_summary", None)
        ):
            raise TypeError("agent must be a compatible Browser Use Agent")

        existing_callback = getattr(agent, "register_new_step_callback")
        if existing_callback is not None and not callable(existing_callback):
            raise TypeError("agent step callback must be callable or None")

        self.agent = agent
        self.goal = goal
        self.config = config_settings
        self.output_root = (
            Path(output_root)
            if output_root is not None
            else config_settings.trace_directory
        )
        self.print_summary = print_summary
        self.final_check = final_check
        self._recording_enabled = config_settings.enabled
        self._open_report = config_settings.open_report
        self.last_trace: _BrowserUseRecorder | None = None
        self._active_trace: _BrowserUseRecorder | None = None
        self._active = False
        self._existing_step_callback = existing_callback

        initial_actions = getattr(agent, "initial_actions", None)
        initial_url = getattr(agent, "initial_url", None)
        if self._recording_enabled and initial_actions and initial_url is None:
            raise ValueError(
                "Browser Use initial_actions run before observable steps; "
                "create the Agent without initial_actions"
            )

        if not self._recording_enabled:
            return

        setattr(agent, "register_new_step_callback", self._on_model_action)
        setattr(agent, "directly_open_url", False)
        if initial_url is not None:
            setattr(agent, "initial_actions", None)
            setattr(agent, "initial_url", None)
        agent_settings.max_actions_per_step = 1

    @property
    def last_report_path(self) -> Path | None:
        if self.last_trace is None:
            return None
        return self.last_trace.report_path

    @property
    def last_session(self) -> ActionSession | None:
        if self.last_trace is None:
            return None
        return self.last_trace.session

    def preflight(self) -> BrowserUsePreflightResult:
        """Check the recording boundary without running the agent."""

        checks: list[BrowserUsePreflightCheck] = []
        if not self._recording_enabled:
            checks.append(
                BrowserUsePreflightCheck(
                    name="recording enabled",
                    passed=False,
                    detail=(
                        "recording is disabled; set enabled = true to create "
                        "a trace"
                    ),
                )
            )
            return BrowserUsePreflightResult(tuple(checks))

        checks.append(
            BrowserUsePreflightCheck(
                name="agent contract",
                passed=True,
                detail="Browser Use run and browser session interfaces are available",
            )
        )
        callback = getattr(self.agent, "register_new_step_callback", None)
        hook_attached = (
            getattr(callback, "__self__", None) is self
            and getattr(callback, "__func__", None)
            is type(self)._on_model_action
            and getattr(self.agent, "directly_open_url", None) is False
            and getattr(
                getattr(self.agent, "settings", None),
                "max_actions_per_step",
                None,
            )
            == 1
        )
        checks.append(
            BrowserUsePreflightCheck(
                name="recording hook",
                passed=hook_attached,
                detail=(
                    "model actions will enter the recorder one step at a time"
                    if hook_attached
                    else (
                        "recording callback or Browser Use action controls are "
                        "not configured"
                    )
                ),
            )
        )
        browser_path = self.config.browser_executable_path
        if browser_path is None:
            browser_detail = "using the Browser Use default executable"
            browser_ok = True
        else:
            browser_ok = browser_path.is_file()
            browser_detail = (
                f"configured executable exists: {browser_path}"
                if browser_ok
                else f"configured executable was not found: {browser_path}"
            )
        checks.append(
            BrowserUsePreflightCheck(
                name="browser executable",
                passed=browser_ok,
                detail=browser_detail,
            )
        )
        checks.append(_preflight_trace_directory(self.output_root))
        checks.append(
            BrowserUsePreflightCheck(
                name="screenshots",
                passed=True,
                detail=(
                    "before/after screenshots are enabled"
                    if self.config.screenshots
                    else "screenshots are disabled; actions and state are still recorded"
                ),
            )
        )
        return BrowserUsePreflightResult(tuple(checks))

    async def run(self, *args: object, **kwargs: object) -> object:
        if self._active:
            raise RuntimeError("an observed Browser Use run is already active")

        if not self._recording_enabled:
            result = self.agent.run(*args, **kwargs)  # type: ignore[attr-defined]
            if not isawaitable(result):
                raise TypeError("Browser Use agent run method must be async")
            return await result

        user_step_end = kwargs.pop("on_step_end", None)
        if user_step_end is not None and not callable(user_step_end):
            raise TypeError("on_step_end must be callable or None")

        trace = _BrowserUseRecorder(
            self._create_trace_directory(),
            self.goal,
            capture_screenshots=self.config.screenshots,
            redact_sensitive_data=self.config.redact_sensitive_data,
            run_state_path=self.output_root / "run-state.json",
        )
        trace.attach_browser_session(self.agent.browser_session)  # type: ignore[attr-defined]
        self.last_trace = trace
        self._active_trace = trace
        self._active = True

        async def on_step_end(agent: object) -> None:
            await trace.on_step_end(agent)
            if user_step_end is not None:
                await _call_callback(user_step_end, agent)

        history: object | None = None
        run_error: BaseException | None = None
        deterministic_verification: VerificationResult | None = None
        deterministic_error_type: str | None = None
        try:
            result = self.agent.run(  # type: ignore[attr-defined]
                *args,
                on_step_end=on_step_end,
                **kwargs,
            )
            if not isawaitable(result):
                raise TypeError("Browser Use agent run method must be async")
            history = await result
            return history
        except BaseException as error:
            run_error = error
            raise
        finally:
            if run_error is None and self.final_check is not None:
                try:
                    state = await trace.final_state()
                    result = self.final_check(state)
                    if isawaitable(result):
                        result = await result
                    if not isinstance(result, VerificationResult):
                        raise TypeError(
                            "final_check must return VerificationResult"
                        )
                    deterministic_verification = result
                except Exception as error:
                    deterministic_error_type = type(error).__name__
            trace.finish(
                history,
                run_error=run_error,
                deterministic_verification=deterministic_verification,
                deterministic_error_type=deterministic_error_type,
            )
            if self._open_report:
                try:
                    self.open_last_report()
                except Exception as error:
                    if self.print_summary:
                        print(
                            "Report could not be opened automatically: "
                            f"{type(error).__name__}"
                        )
            if self.print_summary:
                print(format_session_summary(trace.session, trace.report_path))
            self._active_trace = None
            self._active = False

    def _create_trace_directory(self) -> Path:
        return _new_trace_directory(self.output_root)

    def assert_last_task_passed(self) -> None:
        if self.last_trace is None:
            raise RuntimeError("the observed Browser Use agent has not run yet")
        verification = self.last_trace.session.verification
        report_path = self.last_trace.report_path.resolve()
        if (
            self.config.require_recorded_actions
            and self.last_trace.session.action_count == 0
            and (verification is None or verification.passed)
        ):
            raise AssertionError(
                "Task was not fully observed: no browser actions were "
                "captured while strict recording coverage is enabled. "
                f"Report: {report_path}"
            )
        if verification is None:
            raise AssertionError(
                "Task was not verified by Browser Use. "
                f"Report: {report_path}"
            )
        if not verification.passed:
            raise AssertionError(
                f"Task verification failed: {verification.failure_reason}. "
                f"Report: {report_path}"
            )

    def open_last_report(self) -> Path:
        report_path = self.last_report_path
        if report_path is None:
            raise RuntimeError("the observed Browser Use agent has not run yet")
        return open_local_report(report_path)

    async def _on_model_action(
        self,
        browser_state: object,
        model_output: object,
        step_number: int,
    ) -> None:
        if self._active_trace is not None:
            await self._active_trace.on_model_action(
                browser_state,
                model_output,
                step_number,
            )
        if self._existing_step_callback is not None:
            await _call_callback(
                self._existing_step_callback,
                browser_state,
                model_output,
                step_number,
            )


def observe_browser_use_agent(
    agent: AgentT,
    goal: str | None = None,
    output_root: str | Path | None = None,
    *,
    print_summary: bool | None = None,
    final_check: BrowserUseFinalCheck | None = None,
    config: AgentDevToolsConfig | str | Path | None = None,
) -> ObservedBrowserUseAgent[AgentT]:
    return ObservedBrowserUseAgent(
        agent,
        goal,
        output_root,
        print_summary=print_summary,
        final_check=final_check,
        config=config,
    )


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


def _resolve_agent_goal(agent: object, goal: str | None) -> str:
    if goal is not None:
        return goal

    task = getattr(agent, "task", None)
    if isinstance(task, str) and task.strip():
        return task

    raise ValueError(
        "goal was not provided and the Browser Use agent has no non-empty task; "
        "create the agent with task=... or pass goal explicitly"
    )


async def _call_callback(
    callback: Callable[..., object],
    *args: object,
) -> object:
    result = callback(*args)
    return await result if isawaitable(result) else result


def _new_trace_directory(output_root: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return output_root / f"{timestamp}-{uuid4().hex[:8]}"


def _preflight_trace_directory(output_root: Path) -> BrowserUsePreflightCheck:
    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return BrowserUsePreflightCheck(
            name="trace directory",
            passed=False,
            detail=(
                f"cannot create the trace directory ({type(error).__name__})"
            ),
        )

    probe = output_root / f".agent-devtools-preflight-{uuid4().hex}"
    try:
        probe.write_text("ok", encoding="utf-8")
    except OSError as error:
        return BrowserUsePreflightCheck(
            name="trace directory",
            passed=False,
            detail=(
                f"trace directory is not writable ({type(error).__name__})"
            ),
        )
    try:
        probe.unlink()
    except OSError as error:
        return BrowserUsePreflightCheck(
            name="trace directory",
            passed=False,
            detail=(
                f"trace directory cleanup is not writable ({type(error).__name__})"
            ),
        )
    return BrowserUsePreflightCheck(
        name="trace directory",
        passed=True,
        detail=f"writable: {output_root}",
    )


def _action_from_model_output(
    model_output: object,
    *,
    redact_sensitive_data: bool = True,
) -> tuple[str, dict[str, object]]:
    actions = getattr(model_output, "action", None)
    if not isinstance(actions, list) or not actions:
        return "browser_use_step", {}

    serialized = [_model_dump(action) for action in actions]
    if len(serialized) != 1 or len(serialized[0]) != 1:
        return "browser_use_step", {
            "actions": _json_safe(
                serialized,
                redact_sensitive_data=redact_sensitive_data,
            )
        }

    action_type, arguments = next(iter(serialized[0].items()))
    if not isinstance(arguments, dict):
        arguments = {"value": arguments}
    safe_arguments = _json_safe(
        arguments,
        redact_sensitive_data=redact_sensitive_data,
    )
    return str(action_type), (
        safe_arguments if isinstance(safe_arguments, dict) else {}
    )


def _model_dump(value: object) -> dict[str, object]:
    dump = getattr(value, "model_dump", None)
    if not callable(dump):
        return {"unknown": {}}
    result = dump(exclude_none=True)
    return result if isinstance(result, dict) else {"unknown": {}}


def _latest_action_result(
    agent: object,
    *,
    redact_sensitive_data: bool = True,
) -> tuple[list[str], bool]:
    history = getattr(agent, "history", None)
    items = getattr(history, "history", None)
    if not isinstance(items, list) or not items:
        return [], False
    results = getattr(items[-1], "result", None)
    if not isinstance(results, list):
        return [], False

    errors = [
        _redact_text(error[:2_000]) if redact_sensitive_data else error[:2_000]
        for result in results
        if isinstance((error := getattr(result, "error", None)), str)
        and error.strip()
    ]
    reported_failure = any(
        getattr(result, "success", None) is False for result in results
    )
    return errors, reported_failure


def _history_failure_issue_code(history: object | None) -> RunIssueCode | None:
    items = getattr(history, "history", None)
    if not isinstance(items, list):
        return None
    errors = [
        error.lower()
        for item in items
        for result in (getattr(item, "result", None) or [])
        if isinstance((error := getattr(result, "error", None)), str)
        and error.strip()
    ]
    if not errors:
        return None
    combined = "\n".join(errors)
    if any(
        marker in combined
        for marker in ("api_key_invalid", "api key not valid", "authentication")
    ):
        return RunIssueCode.PROVIDER_CREDENTIALS
    if "rate limit" in combined or "resource_exhausted" in combined:
        return RunIssueCode.PROVIDER_RATE_LIMITED
    if "timeout" in combined:
        return RunIssueCode.PROVIDER_TIMEOUT
    return RunIssueCode.PROVIDER_ERROR


def _history_failure_note(history: object | None) -> str | None:
    issue_code = _history_failure_issue_code(history)
    if issue_code is RunIssueCode.PROVIDER_CREDENTIALS:
        return (
            "Browser Use model provider rejected its credentials. "
            "Check provider setup and API key."
        )
    if issue_code is RunIssueCode.PROVIDER_RATE_LIMITED:
        return (
            "Browser Use model provider rate-limited the run. "
            "Check provider quota and retry policy."
        )
    if issue_code is RunIssueCode.PROVIDER_TIMEOUT:
        return "Browser Use stopped before final judgment after a provider timeout."
    if issue_code is RunIssueCode.PROVIDER_ERROR:
        return (
            "Browser Use stopped before final judgment after a model or runtime "
            "error. Check the agent logs."
        )
    return None


def _page_state(
    state: object,
    *,
    redact_sensitive_data: bool = True,
) -> dict[str, object]:
    browser_errors = getattr(state, "browser_errors", [])
    raw_state = {
        "url": getattr(state, "url", None),
        "title": getattr(state, "title", None),
        "browser_errors": (
            list(browser_errors[:10])
            if isinstance(browser_errors, list)
            else []
        ),
    }
    safe_state = _json_safe(
        raw_state,
        redact_sensitive_data=redact_sensitive_data,
    )
    return safe_state if isinstance(safe_state, dict) else {}


def _navigation_host(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None

    candidate = value.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return None
    if not parsed.scheme and not candidate.startswith("//"):
        parsed = urlsplit(f"//{candidate}")
    try:
        host = parsed.hostname
    except ValueError:
        return None
    return host.lower().rstrip(".") if host else None


def _navigate_verification(
    action_type: str,
    arguments: dict[str, object],
    state_after: dict[str, object],
) -> VerificationResult | None:
    if action_type != "navigate":
        return None

    expected_url = arguments.get("url")
    observed_url = state_after.get("url")
    expected_host = _navigation_host(expected_url)
    observed_host = _navigation_host(observed_url)
    if expected_host is None or observed_host is None:
        return None

    passed = expected_host == observed_host
    return VerificationResult(
        expected_state=f"page host is {expected_host!r}",
        observed_state=(
            f"page host is {observed_host!r}"
            if passed
            else f"page URL is {observed_url!r}"
        ),
        passed=passed,
        failure_reason=(
            None
            if passed
            else (
                f"navigation ended on host {observed_host!r}; "
                f"expected {expected_host!r}"
            )
        ),
        evidence={
            "verification_type": "browser-use-navigation-host",
            "comparison": "hostname",
            "expected_url": expected_url,
            "observed_url": observed_url,
            "expected_host": expected_host,
            "observed_host": observed_host,
        },
    )


def _save_screenshot(
    output_dir: Path,
    relative_path: Path,
    encoded: object,
) -> Path | None:
    if not isinstance(encoded, str) or not encoded.strip():
        return None
    payload = encoded.split(",", 1)[-1]
    try:
        image = base64.b64decode(payload, validate=True)
    except (ValueError, base64.binascii.Error):
        return None
    absolute_path = output_dir / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    absolute_path.write_bytes(image)
    return relative_path


def _judgement(
    history: object | None,
    *,
    redact_sensitive_data: bool = True,
) -> dict[str, object] | None:
    if history is None:
        return None
    get_judgement = getattr(history, "judgement", None)
    if not callable(get_judgement):
        return None
    value = get_judgement()
    if isinstance(value, dict):
        safe_value = _json_safe(
            value,
            redact_sensitive_data=redact_sensitive_data,
        )
        return safe_value if isinstance(safe_value, dict) else None
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        result = dump()
        safe_result = _json_safe(
            result,
            redact_sensitive_data=redact_sensitive_data,
        )
        return safe_result if isinstance(safe_result, dict) else None
    return None


def _judge_verification(
    goal: str | None,
    judgement: dict[str, object] | None,
) -> VerificationResult | None:
    if judgement is None:
        return None
    verdict = judgement.get("verdict")
    if not isinstance(verdict, bool):
        return None
    reasoning = _optional_text(judgement.get("reasoning"))
    provider_failure = _optional_text(judgement.get("failure_reason"))
    observed_state = reasoning or (
        "Browser Use judged the task successful."
        if verdict
        else "Browser Use judged the task unsuccessful."
    )
    failure_reason = None if verdict else provider_failure or observed_state
    return VerificationResult(
        expected_state=goal or "Complete the requested task",
        observed_state=observed_state,
        passed=verdict,
        evidence={
            "judge": "browser-use",
            "impossible_task": judgement.get("impossible_task") is True,
            "reached_captcha": judgement.get("reached_captcha") is True,
        },
        failure_reason=failure_reason,
    )


def _failure_category(reason: str | None) -> FailureCategory:
    if reason is not None and "timeout" in reason.lower():
        return FailureCategory.TIMEOUT
    return FailureCategory.OPERATION_ERROR


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|authorization|password|secret|token|cookie)",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|authorization|password|secret|token)\b\s*[:=]\s*)([^\s,;&]+)"
)
_SECRET_VALUE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{20,}|AQ\.[A-Za-z0-9_-]{20,})\b"
)
_SECRET_QUERY = re.compile(
    r"(?i)([?&](?:api[_-]?key|access[_-]?token|password|secret|token)=[^&#\s]*)"
)


def _json_safe(
    value: object,
    *,
    redact_sensitive_data: bool = False,
) -> object:
    safe_value = json.loads(json.dumps(value, ensure_ascii=False, default=str))
    return _redact_value(safe_value) if redact_sensitive_data else safe_value


def _redact_value(value: object, *, key: str | None = None) -> object:
    if key is not None and _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(child_key): _redact_value(child_value, key=str(child_key))
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _redact_text(value: str) -> str:
    value = _SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", value)
    value = _SECRET_QUERY.sub(
        lambda match: match.group(1).split("=", 1)[0] + "=[REDACTED]",
        value,
    )
    return _SECRET_VALUE.sub("[REDACTED]", value)


__all__ = [
    "BrowserUseFinalCheck",
    "BrowserUseFinalStateCheck",
    "BrowserUsePreflightCheck",
    "BrowserUsePreflightResult",
    "ObservedBrowserUseAgent",
    "observe_browser_use_agent",
]
