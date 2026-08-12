from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import pytest

from agent_devtools import (
    ActionOutcome,
    ActionStatus,
    AgentDevToolsConfig,
    read_session_json,
    read_run_state,
)
from agent_devtools.browser_use import observe_browser_use_agent
from agent_devtools.connection import ConnectionStatus, read_connection_state
from agent_devtools.run_state import RunStateStatus


PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"test-image").decode()


class Settings:
    max_actions_per_step = 5


class State:
    def __init__(self, url: str, title: str) -> None:
        self.url = url
        self.title = title
        self.screenshot = PNG
        self.browser_errors: list[str] = []


class BrowserSession:
    def __init__(self) -> None:
        self.state = State("about:blank", "")

    async def get_browser_state_summary(self) -> State:
        return self.state


class Action:
    def __init__(self, action_type: str, arguments: dict[str, object]) -> None:
        self.action_type = action_type
        self.arguments = arguments

    def model_dump(self, *, exclude_none: bool) -> dict[str, object]:
        return {self.action_type: self.arguments}


class ModelOutput:
    def __init__(self, action_type: str, arguments: dict[str, object]) -> None:
        self.action = [Action(action_type, arguments)]


class Result:
    def __init__(self, *, error: str | None = None) -> None:
        self.error = error
        self.success = None


class HistoryItem:
    def __init__(self, result: list[Result]) -> None:
        self.result = result


class History:
    def __init__(
        self,
        *,
        result: list[Result] | None = None,
        verdict: bool | None = True,
    ) -> None:
        self.history = [HistoryItem(result or [Result()])]
        self.verdict = verdict

    def judgement(self) -> dict[str, object] | None:
        if self.verdict is None:
            return None
        return {
            "verdict": self.verdict,
            "reasoning": "The requested page is open.",
            "failure_reason": None,
            "impossible_task": False,
            "reached_captcha": False,
        }


class Agent:
    def __init__(
        self,
        *,
        action_type: str = "navigate",
        arguments: dict[str, object] | None = None,
        after_url: str = "https://example.com",
        history: History | None = None,
        step_callback: object | None = None,
    ) -> None:
        self.action_type = action_type
        self.arguments = arguments or {"url": "https://example.com"}
        self.after_url = after_url
        self.finished_history = history or History()
        self.history = History()
        self.browser_session = BrowserSession()
        self.register_new_step_callback = step_callback
        self.directly_open_url = True
        self.initial_url = "https://example.com"
        self.initial_actions: list[object] | None = [object()]
        self.settings = Settings()

    async def run(
        self,
        *,
        on_step_end: object,
        max_steps: int = 3,
    ) -> History:
        callback = self.register_new_step_callback
        assert callable(callback)
        callback_result = callback(
            self.browser_session.state,
            ModelOutput(self.action_type, self.arguments),
            1,
        )
        if hasattr(callback_result, "__await__"):
            await callback_result

        self.history = History()
        self.browser_session.state = State(
            self.after_url,
            "Example Domain",
        )
        assert callable(on_step_end)
        step_end_result = on_step_end(self)
        if hasattr(step_end_result, "__await__"):
            await step_end_result
        return self.finished_history


class ProviderFailureAgent(Agent):
    async def run(
        self,
        *,
        on_step_end: object,
        max_steps: int = 3,
    ) -> History:
        return self.finished_history


class RunFailureAgent(Agent):
    async def run(
        self,
        *,
        on_step_end: object,
        max_steps: int = 3,
    ) -> History:
        raise RuntimeError("secret-browser-use-agent-detail")


class IncompatibleAsyncAgent:
    async def run(self) -> None:
        pass


def test_observer_records_navigation_with_one_setup_call(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        raw_agent = Agent()
        agent = observe_browser_use_agent(
            raw_agent,
            "Open example.com",
            tmp_path,
        )

        history = await agent.run(max_steps=3)
        agent.assert_last_task_passed()

        assert history is raw_agent.finished_history
        assert raw_agent.directly_open_url is False
        assert raw_agent.initial_url is None
        assert raw_agent.initial_actions is None
        assert raw_agent.settings.max_actions_per_step == 1
        assert agent.last_report_path is not None

        session = read_session_json(agent.last_report_path.parent / "session.json")
        assert session.action_count == 1
        assert session.actions[0].action_type == "navigate"
        assert session.actions[0].arguments == {
            "url": "https://example.com",
            "browser_use_step": 1,
        }
        assert session.actions[0].status is ActionStatus.SUCCESS
        assert session.actions[0].screenshot_before is not None
        assert session.actions[0].screenshot_after is not None
        assert session.actions[0].verification is not None
        assert session.actions[0].verification.passed is True
        assert session.actions[0].verification.evidence["comparison"] == (
            "hostname"
        )
        assert session.outcome is ActionOutcome.SUCCESS
        state = read_run_state(tmp_path / "run-state.json")
        assert state.status is RunStateStatus.PASSED
        assert state.action_count == 1
        assert state.last_action_type == "navigate"
        assert state.report_path is not None
        assert state.report_path.name == "report.html"
        connection = read_connection_state(tmp_path / "connection-state.json")
        assert connection.status is ConnectionStatus.CONNECTED
        assert connection.observer_kind == "browser-use"

    asyncio.run(run())


def test_observer_preflight_checks_hook_and_trace_directory(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        trace_root = tmp_path / "trace"
        agent = observe_browser_use_agent(
            Agent(),
            "Open example.com",
            config=AgentDevToolsConfig(
                trace_directory=trace_root,
            ),
        )

        result = agent.preflight()

        assert result.passed is True
        assert [check.name for check in result.checks] == [
            "agent contract",
            "recording hook",
            "browser executable",
            "trace directory",
            "screenshots",
        ]
        assert not list(trace_root.iterdir())

    asyncio.run(run())


def test_observer_preflight_rejects_disabled_recording(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        agent = observe_browser_use_agent(
            Agent(),
            "Open example.com",
            config=AgentDevToolsConfig(
                enabled=False,
                trace_directory=tmp_path / "trace",
            ),
        )

        result = agent.preflight()

        assert result.passed is False
        assert result.checks[0].name == "recording enabled"
        assert "enabled = true" in result.checks[0].detail

    asyncio.run(run())


def test_observer_preflight_reports_unwritable_trace_path(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "trace-file"
    trace_path.write_text("not a directory", encoding="utf-8")

    async def run() -> None:
        agent = observe_browser_use_agent(
            Agent(),
            "Open example.com",
            config=AgentDevToolsConfig(trace_directory=trace_path),
        )

        result = agent.preflight()

        assert result.passed is False
        trace_check = next(
            check for check in result.checks if check.name == "trace directory"
        )
        assert trace_check.passed is False
        assert "FileExistsError" in trace_check.detail

    asyncio.run(run())


def test_observer_marks_navigation_to_another_host_as_action_failure(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        raw_agent = Agent(after_url="https://wrong.example")
        agent = observe_browser_use_agent(
            raw_agent,
            "Open example.com",
            tmp_path,
        )

        await agent.run(max_steps=3)

        assert agent.last_session is not None
        action = agent.last_session.actions[0]
        assert action.status is ActionStatus.SUCCESS
        assert action.verification is not None
        assert action.verification.passed is False
        assert "wrong.example" in (action.verification.failure_reason or "")
        assert action.outcome is ActionOutcome.FAILURE
        report_path = agent.last_report_path
        assert report_path is not None
        report = report_path.read_text(encoding="utf-8")
        assert "browser-use-navigation-host" in report
        assert "Action check" in report

    asyncio.run(run())


def test_observer_leaves_navigation_unverified_without_http_url(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        raw_agent = Agent(
            arguments={"url": "file:///tmp/example.html"},
            after_url="file:///tmp/example.html",
        )
        agent = observe_browser_use_agent(
            raw_agent,
            "Open the local page",
            tmp_path,
        )

        await agent.run(max_steps=3)

        assert agent.last_session is not None
        action = agent.last_session.actions[0]
        assert action.status is ActionStatus.SUCCESS
        assert action.verification is None
        assert action.outcome is ActionOutcome.UNVERIFIED

    asyncio.run(run())


def test_observer_redacts_common_credentials_from_trace_metadata(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        raw_agent = Agent(
            arguments={
                "url": "https://example.com/?token=private-token",
                "headers": {"authorization": "Bearer private-token"},
            }
        )
        agent = observe_browser_use_agent(
            raw_agent,
            "Open example.com with token=private-token",
            tmp_path,
            config=AgentDevToolsConfig(redact_sensitive_data=True),
        )

        await agent.run(max_steps=3)

        report_path = agent.last_report_path
        assert report_path is not None
        session_path = report_path.parent / "session.json"
        session = read_session_json(session_path)
        serialized = session_path.read_text(encoding="utf-8")
        assert session.actions[0].arguments["url"] == (
            "https://example.com/?token=[REDACTED]"
        )
        assert session.actions[0].arguments["headers"] == {
            "authorization": "[REDACTED]"
        }
        assert "private-token" not in serialized

    asyncio.run(run())


def test_observer_reads_goal_from_wrapped_agent_task(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        raw_agent = Agent()
        raw_agent.task = "Open the product page"
        agent = observe_browser_use_agent(
            raw_agent,
            output_root=tmp_path,
            print_summary=False,
        )

        await agent.run()

        assert agent.goal == "Open the product page"
        assert agent.last_session is not None
        assert agent.last_session.goal == "Open the product page"

    asyncio.run(run())


def test_open_last_report_uses_default_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[tuple[str, int]] = []

    def open_browser(url: str, *, new: int) -> bool:
        opened.append((url, new))
        return True

    async def run() -> None:
        agent = observe_browser_use_agent(
            Agent(),
            "Open example.com",
            tmp_path,
        )
        await agent.run()

        monkeypatch.setattr(
            "agent_devtools.report_opening.webbrowser.open",
            open_browser,
        )
        monkeypatch.setattr(
            "agent_devtools.report_opening._is_wsl",
            lambda: False,
        )
        report_path = agent.open_last_report()

        assert report_path.is_absolute()
        assert opened == [(report_path.as_uri(), 2)]

    asyncio.run(run())


def test_open_last_report_requires_a_completed_run(tmp_path: Path) -> None:
    agent = observe_browser_use_agent(
        Agent(),
        "Open example.com",
        tmp_path,
    )

    with pytest.raises(RuntimeError, match="has not run yet"):
        agent.open_last_report()


def test_observer_prints_a_compact_run_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def run() -> None:
        agent = observe_browser_use_agent(
            Agent(),
            "Open example.com",
            tmp_path,
        )
        await agent.run()

        output = capsys.readouterr().out
        assert "Agent DevTools\n" in output
        assert "Task result: SUCCESS" in output
        assert "Actions: 1 (1 succeeded, 0 failed)" in output
        assert "Final check: passed" in output
        assert f"Report: {agent.last_report_path.resolve()}" in output

    asyncio.run(run())


def test_observer_can_disable_the_run_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def run() -> None:
        agent = observe_browser_use_agent(
            Agent(),
            "Open example.com",
            tmp_path,
            print_summary=False,
        )
        await agent.run()

        assert capsys.readouterr().out == ""

    asyncio.run(run())


def test_observer_reads_configured_trace_root_and_can_skip_screenshots(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def run() -> None:
        trace_root = tmp_path / "configured-trace"
        config = AgentDevToolsConfig(
            screenshots=False,
            terminal_summary=False,
            trace_directory=trace_root,
        )
        agent = observe_browser_use_agent(
            Agent(),
            "Open example.com",
            config=config,
        )

        await agent.run()

        report = agent.last_report_path
        assert report is not None
        assert report.parent.parent == trace_root
        session = read_session_json(report.parent / "session.json")
        assert session.actions[0].screenshot_before is None
        assert session.actions[0].screenshot_after is None
        assert not list(report.parent.rglob("*.png"))
        assert capsys.readouterr().out == ""

    asyncio.run(run())


def test_disabled_config_passes_through_without_creating_a_trace(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        raw_agent = ProviderFailureAgent()
        agent = observe_browser_use_agent(
            raw_agent,
            "Open example.com",
            config=AgentDevToolsConfig(
                enabled=False,
                trace_directory=tmp_path / "should-not-exist",
            ),
        )

        await agent.run(on_step_end=None)

        assert agent.last_report_path is None
        assert raw_agent.directly_open_url is True
        assert raw_agent.initial_actions is not None
        assert raw_agent.settings.max_actions_per_step == 5
        assert not (tmp_path / "should-not-exist").exists()

    asyncio.run(run())


def test_config_can_open_the_report_automatically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[tuple[str, int]] = []

    def open_browser(url: str, *, new: int) -> bool:
        opened.append((url, new))
        return True

    monkeypatch.setattr(
        "agent_devtools.report_opening.webbrowser.open",
        open_browser,
    )
    monkeypatch.setattr(
        "agent_devtools.report_opening._is_wsl",
        lambda: False,
    )

    async def run() -> None:
        agent = observe_browser_use_agent(
            Agent(),
            "Open example.com",
            output_root=tmp_path,
            config=AgentDevToolsConfig(open_report=True),
        )
        await agent.run()

        report = agent.last_report_path
        assert report is not None
        assert opened == [(report.resolve().as_uri(), 2)]

    asyncio.run(run())


def test_observer_preserves_existing_callbacks(tmp_path: Path) -> None:
    async def run() -> None:
        callback_steps: list[int] = []
        step_end_calls = 0

        def existing_step_callback(
            state: object,
            output: object,
            step_number: int,
        ) -> None:
            callback_steps.append(step_number)

        async def existing_step_end(agent: object) -> None:
            nonlocal step_end_calls
            step_end_calls += 1

        agent = observe_browser_use_agent(
            Agent(step_callback=existing_step_callback),
            "Open example.com",
            tmp_path,
        )

        await agent.run(on_step_end=existing_step_end)

        assert callback_steps == [1]
        assert step_end_calls == 1

    asyncio.run(run())


def test_done_step_is_not_recorded_as_a_computer_action(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        agent = observe_browser_use_agent(
            Agent(action_type="done", arguments={"success": True}),
            "Complete the task",
            tmp_path,
        )

        await agent.run()

        assert agent.last_session is not None
        assert agent.last_session.action_count == 0
        assert agent.last_session.outcome is ActionOutcome.SUCCESS

    asyncio.run(run())


def test_strict_coverage_rejects_zero_action_success(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        agent = observe_browser_use_agent(
            Agent(action_type="done", arguments={"success": True}),
            "Complete the task",
            tmp_path,
            config=AgentDevToolsConfig(
                require_recorded_actions=True,
            ),
        )

        await agent.run()

        assert agent.last_session is not None
        assert agent.last_session.action_count == 0
        assert agent.last_session.verification is not None
        assert agent.last_session.verification.passed is True
        with pytest.raises(AssertionError, match="no browser actions"):
            agent.assert_last_task_passed()

    asyncio.run(run())


def test_auxiliary_file_actions_are_separate_from_browser_timeline(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        agent = observe_browser_use_agent(
            Agent(
                action_type="write_file",
                arguments={"file_name": "todo.md", "content": "done"},
            ),
            "Complete the task",
            tmp_path,
            print_summary=False,
        )

        await agent.run()

        assert agent.last_session is not None
        assert agent.last_session.action_count == 0
        assert len(agent.last_session.auxiliary_events) == 1
        assert (
            agent.last_session.auxiliary_events[0]["action_type"]
            == "write_file"
        )
        report = agent.last_report_path
        assert report is not None
        report_text = report.read_text(encoding="utf-8")
        assert "Agent auxiliary events (1)" in report_text
        assert "write_file" in report_text
        assert "No actions recorded." in report_text

    asyncio.run(run())


def test_provider_failure_is_clear_without_storing_secret_details(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        raw_agent = ProviderFailureAgent(
            history=History(
                result=[Result(error="API key not valid: secret-provider-detail")],
                verdict=None,
            )
        )
        agent = observe_browser_use_agent(
            raw_agent,
            "Open example.com",
            tmp_path,
        )

        await agent.run()

        assert agent.last_session is not None
        assert agent.last_session.outcome is ActionOutcome.UNVERIFIED
        assert agent.last_session.verification_note is not None
        assert "rejected its credentials" in agent.last_session.verification_note
        assert agent.last_session.issue_code == "provider_credentials"
        report = agent.last_report_path
        assert report is not None
        trace_text = (report.parent / "session.json").read_text(encoding="utf-8")
        trace_text += report.read_text(encoding="utf-8")
        assert '"issue_code": "provider_credentials"' in trace_text
        assert "secret-provider-detail" not in trace_text

    asyncio.run(run())


def test_agent_run_failure_is_clear_without_storing_secret_details(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        agent = observe_browser_use_agent(
            RunFailureAgent(),
            "Open example.com",
            tmp_path,
            print_summary=False,
        )

        with pytest.raises(RuntimeError, match="secret-browser-use-agent-detail"):
            await agent.run()

        assert agent.last_session is not None
        assert agent.last_session.verification_source == "agent-run"
        assert agent.last_session.verification_note == (
            "Browser Use agent run failed (RuntimeError)."
        )
        report = agent.last_report_path
        assert report is not None
        report_text = report.read_text(encoding="utf-8")
        session_text = (report.parent / "session.json").read_text(encoding="utf-8")
        assert "Agent run failure" in report_text
        assert "secret-browser-use-agent-detail" not in report_text
        assert "secret-browser-use-agent-detail" not in session_text

    asyncio.run(run())


def test_observer_validates_agent_and_goal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="goal cannot be empty"):
        observe_browser_use_agent(Agent(), "  ", tmp_path)

    with pytest.raises(ValueError, match="no non-empty task"):
        observe_browser_use_agent(Agent(), output_root=tmp_path)

    with pytest.raises(TypeError, match="callable async run method"):
        observe_browser_use_agent(object(), "Open example.com", tmp_path)

    with pytest.raises(TypeError, match="compatible Browser Use Agent"):
        observe_browser_use_agent(
            IncompatibleAsyncAgent(),
            "Open example.com",
            tmp_path,
        )


def test_observer_rejects_unobservable_explicit_initial_actions(
    tmp_path: Path,
) -> None:
    raw_agent = Agent()
    raw_agent.initial_url = None

    with pytest.raises(ValueError, match="initial_actions"):
        observe_browser_use_agent(raw_agent, "Open example.com", tmp_path)
