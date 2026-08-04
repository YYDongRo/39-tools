import asyncio
from pathlib import Path

import pytest

from agent_devtools import (
    VerificationResult,
    observe_agent,
    observe_async_agent,
)


class Tools:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def click(self, selector: str) -> str:
        self.calls.append(selector)
        return "clicked"


class AsyncTools:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def click(self, selector: str) -> str:
        self.calls.append(selector)
        await asyncio.sleep(0)
        return "clicked"


class Agent:
    def __init__(self, task: str) -> None:
        self.task = task
        self.received_task: str | None = None

    def run(self, user_request: str, *, tools: Tools) -> str:
        self.received_task = user_request
        return tools.click("#target")


class AsyncAgent:
    def __init__(self, task: str) -> None:
        self.task = task
        self.received_task: str | None = None

    async def run(self, user_request: str, *, tools: AsyncTools) -> str:
        self.received_task = user_request
        return await tools.click("#target")


class AgentWithoutTask:
    def run(self, user_request: str, *, tools: Tools) -> str:
        return tools.click(user_request)


def test_observed_agent_reads_task_once_and_records_tool_actions(
    tmp_path: Path,
) -> None:
    raw_agent = Agent("Click the target")
    tools = Tools()
    captured: list[Path] = []

    def capture_screenshot(path: Path) -> None:
        path.write_text("deterministic evidence", encoding="utf-8")
        captured.append(path)

    def observe_state() -> dict[str, object]:
        return {"click_count": len(tools.calls)}

    observed = observe_agent(
        raw_agent,
        tools,
        tmp_path / "trace",
        capture_screenshot=capture_screenshot,
        observe_state=observe_state,
        task_verification=lambda: VerificationResult(
            expected_state="target clicked",
            observed_state="target clicked",
            passed=True,
        ),
    )

    assert observed.run() == "clicked"

    assert raw_agent.received_task == "Click the target"
    assert observed.last_trace is not None
    assert observed.last_trace.session.goal == "Click the target"
    assert observed.last_trace.session.action_count == 1
    action = observed.last_trace.session.actions[0]
    assert action.action_type == "click"
    assert action.arguments == {"selector": "#target"}
    assert action.screenshot_before is not None
    assert action.screenshot_after is not None
    assert all(path.is_file() for path in captured)
    assert action.observations["state_changes"] == ["click_count"]
    observed.assert_last_task_passed()
    assert observed.last_report_path is not None
    assert observed.last_report_path.is_file()


def test_observed_agent_accepts_explicit_task_for_agent_without_task(
    tmp_path: Path,
) -> None:
    raw_agent = AgentWithoutTask()
    observed = observe_agent(
        raw_agent,
        Tools(),
        tmp_path / "trace",
        task="Use the explicit task",
    )

    observed.run()

    assert observed.last_trace is not None
    assert observed.last_trace.session.goal == "Use the explicit task"


def test_observed_agent_rejects_missing_task(tmp_path: Path) -> None:
    observed = observe_agent(AgentWithoutTask(), Tools(), tmp_path / "trace")

    with pytest.raises(ValueError, match="agent task is unavailable"):
        observed.run()

    assert list(tmp_path.iterdir()) == []


def test_observed_async_agent_reads_task_and_records_async_actions(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        raw_agent = AsyncAgent("Click the target asynchronously")
        tools = AsyncTools()
        observed = observe_async_agent(raw_agent, tools, tmp_path / "trace")

        assert await observed.run() == "clicked"

        assert raw_agent.received_task == "Click the target asynchronously"
        assert observed.last_trace is not None
        assert observed.last_trace.session.action_count == 1
        assert observed.last_trace.session.actions[0].action_type == "click"
        assert observed.last_report_path is not None
        assert observed.last_report_path.is_file()

    asyncio.run(run())


def test_observed_agent_owns_tools_argument(tmp_path: Path) -> None:
    observed = observe_agent(Agent("Run once"), Tools(), tmp_path / "trace")

    with pytest.raises(ValueError, match="owns the tools argument"):
        observed.run(tools=Tools())

