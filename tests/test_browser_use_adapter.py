from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import pytest

from agent_devtools import ActionOutcome, ActionStatus, read_session_json
from agent_devtools.browser_use import observe_browser_use_agent


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
        history: History | None = None,
        step_callback: object | None = None,
    ) -> None:
        self.action_type = action_type
        self.arguments = arguments or {"url": "https://example.com"}
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
            "https://example.com",
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
        assert session.outcome is ActionOutcome.SUCCESS

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
            "agent_devtools.integrations.browser_use.webbrowser.open",
            open_browser,
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
        report = agent.last_report_path
        assert report is not None
        trace_text = (report.parent / "session.json").read_text(encoding="utf-8")
        trace_text += report.read_text(encoding="utf-8")
        assert "secret-provider-detail" not in trace_text

    asyncio.run(run())


def test_observer_validates_agent_and_goal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="goal cannot be empty"):
        observe_browser_use_agent(Agent(), "  ", tmp_path)

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
