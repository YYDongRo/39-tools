import asyncio
from pathlib import Path

import pytest

from agent_devtools.playwright import (
    FinalPageState,
    observe_async_playwright_agent,
    observe_playwright_agent,
)
from agent_devtools.verification import VerificationResult


class Agent:
    def run(self, user_request: str, *, tools: object) -> None:
        pass


class MissingRun:
    pass


class Page:
    def evaluate(
        self,
        script: str,
        arguments: dict[str, int],
    ) -> dict[str, object]:
        return {
            "url": "https://example.com/done",
            "title": "Done",
            "headings": ["Task complete"],
            "visible_text": "Task complete",
            "text_truncated": False,
        }


class AsyncAgent:
    async def run(self, user_request: str, *, tools: object) -> str:
        return f"handled: {user_request}"


class FailingAsyncAgent:
    async def run(self, user_request: str, *, tools: object) -> None:
        raise RuntimeError("secret-playwright-agent-detail")


class AsyncPage:
    async def evaluate(
        self,
        script: str,
        arguments: dict[str, int],
    ) -> dict[str, object]:
        return Page().evaluate(script, arguments)


def test_observed_agent_requires_run_method(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="callable run method"):
        observe_playwright_agent(
            MissingRun(),
            object(),
            object(),
            tmp_path,
        )


def test_observed_agent_rejects_invalid_generator(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="expectation_generator"):
        observe_playwright_agent(
            Agent(),
            object(),
            object(),
            tmp_path,
            expectation_generator="invalid",  # type: ignore[arg-type]
        )


def test_observed_agent_rejects_invalid_final_state_verifier(
    tmp_path: Path,
) -> None:
    with pytest.raises(TypeError, match="final_state_verifier"):
        observe_playwright_agent(
            Agent(),
            object(),
            object(),
            tmp_path,
            final_state_verifier="invalid",  # type: ignore[arg-type]
        )


def test_observed_agent_rejects_two_automatic_verification_modes(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="either expectation_generator"):
        observe_playwright_agent(
            Agent(),
            object(),
            object(),
            tmp_path,
            expectation_generator=lambda request: None,
            final_state_verifier=lambda request, state: None,
        )


def test_observed_agent_validates_request_before_creating_trace(
    tmp_path: Path,
) -> None:
    observed_agent = observe_playwright_agent(
        Agent(),
        object(),
        object(),
        tmp_path,
    )

    with pytest.raises(ValueError, match="user_request cannot be empty"):
        observed_agent.run("  ")

    assert observed_agent.last_report_path is None
    assert list(tmp_path.iterdir()) == []


def test_observed_agent_owns_tools_argument(tmp_path: Path) -> None:
    observed_agent = observe_playwright_agent(
        Agent(),
        object(),
        object(),
        tmp_path,
    )

    with pytest.raises(ValueError, match="owns the tools argument"):
        observed_agent.run("Do the task", tools=object())


def test_observed_agent_cannot_assert_before_first_run(tmp_path: Path) -> None:
    observed_agent = observe_playwright_agent(
        Agent(),
        object(),
        object(),
        tmp_path,
    )

    with pytest.raises(RuntimeError, match="has not run yet"):
        observed_agent.assert_last_task_passed()


def test_observed_agent_automatically_verifies_the_final_page(
    tmp_path: Path,
) -> None:
    observed_state: FinalPageState | None = None

    def verify(
        user_request: str,
        state: FinalPageState,
    ) -> VerificationResult:
        nonlocal observed_state
        observed_state = state
        return VerificationResult(
            expected_state=user_request,
            observed_state="The task complete heading is visible.",
            passed=True,
            evidence={"assessment_type": "ai_final_state"},
        )

    observed_agent = observe_playwright_agent(
        Agent(),
        object(),
        Page(),
        tmp_path,
        final_state_verifier=verify,
        capture_browser_events=False,
    )

    observed_agent.run("Complete the task")

    assert observed_state is not None
    assert observed_state.headings == ("Task complete",)
    assert observed_agent.last_trace is not None
    assert observed_agent.last_trace.session.verification is not None
    assert observed_agent.last_trace.session.verification.passed is True
    assert observed_agent.last_trace.session.verification_source == (
        "custom:function:final-state"
    )
    assert observed_agent.last_report_path is not None
    report = observed_agent.last_report_path.read_text(encoding="utf-8")
    assert "AI task assessment" in report


def test_final_state_verifier_failure_leaves_the_run_unverified(
    tmp_path: Path,
) -> None:
    def fail(user_request: str, state: FinalPageState) -> None:
        raise RuntimeError(f"secret-provider-detail: {user_request}")

    observed_agent = observe_playwright_agent(
        Agent(),
        object(),
        Page(),
        tmp_path,
        final_state_verifier=fail,
        capture_browser_events=False,
    )

    observed_agent.run("Complete the task")

    assert observed_agent.last_trace is not None
    session = observed_agent.last_trace.session
    assert session.verification is None
    assert session.verification_note is not None
    assert "RuntimeError" in session.verification_note
    assert "secret-provider-detail" not in session.verification_note


def test_async_observed_agent_automatically_verifies_the_final_page(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        async def verify(
            user_request: str,
            state: FinalPageState,
        ) -> VerificationResult:
            return VerificationResult(
                expected_state=user_request,
                observed_state=state.title,
                passed=True,
                evidence={"assessment_type": "ai_final_state"},
            )

        observed_agent = observe_async_playwright_agent(
            AsyncAgent(),
            object(),
            AsyncPage(),
            tmp_path,
            final_state_verifier=verify,
            capture_browser_events=False,
        )

        result = await observed_agent.run("Complete the task")

        assert result == "handled: Complete the task"
        assert observed_agent.last_trace is not None
        assert observed_agent.last_trace.session.verification is not None
        assert observed_agent.last_trace.session.verification.passed is True

    asyncio.run(run())


def test_async_playwright_agent_records_agent_run_failure(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        observed_agent = observe_async_playwright_agent(
            FailingAsyncAgent(),
            object(),
            AsyncPage(),
            tmp_path,
            capture_browser_events=False,
        )

        with pytest.raises(RuntimeError, match="secret-playwright-agent-detail"):
            await observed_agent.run("Complete the task")

        assert observed_agent.last_trace is not None
        session = observed_agent.last_trace.session
        assert session.verification_source == "agent-run"
        assert session.verification_note == "Agent run failed (RuntimeError)."
        report = observed_agent.last_report_path
        assert report is not None
        report_text = report.read_text(encoding="utf-8")
        assert "Agent run failure" in report_text
        assert "secret-playwright-agent-detail" not in report_text

    asyncio.run(run())
