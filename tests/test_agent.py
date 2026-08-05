import asyncio
from pathlib import Path

import pytest

from agent_devtools import (
    FinalStateObservation,
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


class FailingAgent:
    task = "Click the target"

    def run(self, user_request: str, *, tools: Tools) -> None:
        tools.click("#target")
        raise RuntimeError("secret-agent-detail")


class FailingAsyncAgent:
    task = "Click the target asynchronously"

    async def run(self, user_request: str, *, tools: AsyncTools) -> None:
        await tools.click("#target")
        raise RuntimeError("secret-async-agent-detail")


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


def test_observed_agent_records_sanitized_agent_run_failure(
    tmp_path: Path,
) -> None:
    observed = observe_agent(FailingAgent(), Tools(), tmp_path / "trace")

    with pytest.raises(RuntimeError, match="secret-agent-detail"):
        observed.run()

    assert observed.last_trace is not None
    session = observed.last_trace.session
    assert session.verification_source == "agent-run"
    assert session.verification_note == "Agent run failed (RuntimeError)."
    assert session.outcome.value == "unverified"
    report = observed.last_report_path
    assert report is not None
    report_text = report.read_text(encoding="utf-8")
    assert "Agent run failed" in report_text
    assert "Agent run failure" in report_text
    assert "secret-agent-detail" not in report_text


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


def test_observed_async_agent_records_sanitized_agent_run_failure(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        observed = observe_async_agent(
            FailingAsyncAgent(),
            AsyncTools(),
            tmp_path / "trace",
        )

        with pytest.raises(RuntimeError, match="secret-async-agent-detail"):
            await observed.run()

        assert observed.last_trace is not None
        session = observed.last_trace.session
        assert session.verification_source == "agent-run"
        assert session.verification_note == "Agent run failed (RuntimeError)."
        report = observed.last_report_path
        assert report is not None
        report_text = report.read_text(encoding="utf-8")
        assert "Agent run failed" in report_text
        assert "secret-async-agent-detail" not in report_text

    asyncio.run(run())


def test_observed_agent_owns_tools_argument(tmp_path: Path) -> None:
    observed = observe_agent(Agent("Run once"), Tools(), tmp_path / "trace")

    with pytest.raises(ValueError, match="owns the tools argument"):
        observed.run(tools=Tools())


def test_observed_agent_passes_final_state_to_verifier(
    tmp_path: Path,
) -> None:
    tools = Tools()
    captured: list[Path] = []
    received: FinalStateObservation | None = None

    def capture_screenshot(path: Path) -> None:
        path.write_text("final-state evidence", encoding="utf-8")
        captured.append(path)

    def verify(observation: FinalStateObservation) -> VerificationResult:
        nonlocal received
        received = observation
        return VerificationResult(
            expected_state="target clicked",
            observed_state=f"{observation.state}",
            passed=observation.state == {"click_count": 1},
        )

    observed = observe_agent(
        Agent("Click the target"),
        tools,
        tmp_path / "trace",
        capture_screenshot=capture_screenshot,
        observe_state=lambda: {"click_count": len(tools.calls)},
        final_state_verifier=verify,
    )

    assert observed.run() == "clicked"
    assert received is not None
    assert received.task == "Click the target"
    assert received.action_count == 1
    assert received.actions[0].action_type == "click"
    assert received.screenshot_path is not None
    assert received.screenshot_path.is_file()
    assert received.trace_directory is not None
    assert received.trace_directory.is_dir()
    assert captured
    assert observed.last_trace is not None
    assert observed.last_trace.session.verification_source == (
        "generic:final-state"
    )
    assert observed.last_trace.session.outcome.value == "success"


def test_final_state_verifier_failure_is_a_task_failure(
    tmp_path: Path,
) -> None:
    observed = observe_agent(
        Agent("Click the target"),
        Tools(),
        tmp_path / "trace",
        final_state_verifier=lambda observation: VerificationResult(
            expected_state="target is enabled",
            observed_state="target is not enabled",
            passed=False,
            failure_reason="the target remained disabled",
        ),
    )

    observed.run()

    assert observed.last_trace is not None
    session = observed.last_trace.session
    assert all(action.status.value == "success" for action in session.actions)
    assert session.verification is not None
    assert session.verification.passed is False
    assert session.outcome.value == "failure"


def test_final_state_verifier_error_leaves_task_unverified(
    tmp_path: Path,
) -> None:
    def verify(_: FinalStateObservation) -> VerificationResult:
        raise RuntimeError("secret-judge-detail")

    observed = observe_agent(
        Agent("Click the target"),
        Tools(),
        tmp_path / "trace",
        final_state_verifier=verify,
    )

    assert observed.run() == "clicked"
    assert observed.last_trace is not None
    session = observed.last_trace.session
    assert session.verification is None
    assert session.verification_source == "generic:final-state"
    assert session.verification_note == (
        "Final-state verification unavailable (RuntimeError)."
    )
    assert session.outcome.value == "unverified"
    assert observed.last_report_path is not None
    assert "secret-judge-detail" not in observed.last_report_path.read_text(
        encoding="utf-8"
    )


def test_observed_agent_rejects_two_task_verification_modes(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="either task_verification"):
        observe_agent(
            Agent("Click the target"),
            Tools(),
            tmp_path / "trace",
            task_verification=lambda: VerificationResult(
                expected_state="done",
                observed_state="done",
                passed=True,
            ),
            final_state_verifier=lambda _: VerificationResult(
                expected_state="done",
                observed_state="done",
                passed=True,
            ),
        )


def test_observed_async_agent_supports_async_final_state_verifier(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        async def verify(
            observation: FinalStateObservation,
        ) -> VerificationResult:
            return VerificationResult(
                expected_state="target clicked",
                observed_state=str(observation.state),
                passed=observation.action_count == 1,
            )

        observed = observe_async_agent(
            AsyncAgent("Click the target asynchronously"),
            AsyncTools(),
            tmp_path / "trace",
            observe_state=lambda: {"ready": True},
            final_state_verifier=verify,
        )

        assert await observed.run() == "clicked"
        assert observed.last_trace is not None
        assert observed.last_trace.session.verification is not None
        assert observed.last_trace.session.verification.passed is True

    asyncio.run(run())
