from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from agent_devtools.browser_use import (
    BrowserUseFinalStateCheck,
    EvaluationRunStatus,
    evaluate_browser_use_agent,
)
from agent_devtools.config import AgentDevToolsConfig
from agent_devtools.evaluation_comparison_serialization import (
    read_evaluation_comparison_json,
)
from agent_devtools.evaluation_serialization import read_evaluation_json
from agent_devtools.serialization import read_session_json


class _Settings:
    max_actions_per_step = 5


class _State:
    def __init__(self, url: str = "about:blank") -> None:
        self.url = url
        self.title = "Evaluation fixture"
        self.screenshot = None
        self.browser_errors: list[str] = []


class _BrowserSession:
    def __init__(self) -> None:
        self.state = _State()

    async def get_browser_state_summary(self) -> _State:
        return self.state


class _Action:
    def model_dump(self, *, exclude_none: bool) -> dict[str, object]:
        return {"navigate": {"url": "https://shop.example.test/product"}}


class _ModelOutput:
    action = [_Action()]


class _Result:
    error = None
    success = True


class _Item:
    result = [_Result()]


class _History:
    def __init__(self, verdict: bool | None) -> None:
        self.verdict = verdict
        self.history = [_Item()]

    def judgement(self) -> dict[str, object] | None:
        if self.verdict is None:
            return None
        return {
            "verdict": self.verdict,
            "reasoning": (
                "The correct product is open."
                if self.verdict
                else "The wrong product is open."
            ),
            "failure_reason": (
                None if self.verdict else "The requested product was not opened."
            ),
            "impossible_task": False,
            "reached_captcha": False,
        }


class _Agent:
    def __init__(
        self,
        *,
        verdict: bool | None = True,
        run_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.verdict = verdict
        self.run_error = run_error
        self.close_error = close_error
        self.close_count = 0
        self.register_new_step_callback = None
        self.directly_open_url = True
        self.initial_url = None
        self.initial_actions = None
        self.settings = _Settings()
        self.browser_session = _BrowserSession()
        self.history = _History(verdict)

    async def run(self, *, on_step_end: object, max_steps: int) -> _History:
        if self.run_error is not None:
            raise self.run_error
        callback = self.register_new_step_callback
        assert callable(callback)
        await callback(self.browser_session.state, _ModelOutput(), 1)
        self.browser_session.state = _State(
            "https://shop.example.test/product"
        )
        assert callable(on_step_end)
        await on_step_end(self)
        return _History(self.verdict)

    async def close(self) -> None:
        self.close_count += 1
        if self.close_error is not None:
            raise self.close_error


def test_evaluator_creates_numbered_traces_and_closes_fresh_agents(
    tmp_path: Path,
) -> None:
    agents: list[_Agent] = []

    async def factory(task: str) -> _Agent:
        assert task == "Open the product."
        agent = _Agent()
        agents.append(agent)
        return agent

    evaluation = asyncio.run(
        evaluate_browser_use_agent(
            agent_factory=factory,
            task="Open the product.",
            runs=2,
            max_steps=4,
            output_root=tmp_path / "evaluations",
        )
    )

    assert evaluation.passed_count == 2
    assert evaluation.representative_success_run_number == 1
    assert len({id(agent) for agent in agents}) == 2
    assert [agent.close_count for agent in agents] == [1, 1]
    assert [run.trace_directory.as_posix() for run in evaluation.runs] == [
        "runs/001",
        "runs/002",
    ]
    for number in (1, 2):
        trace = evaluation.output_dir / "runs" / f"{number:03d}"
        assert (trace / "session.json").is_file()
        assert (trace / "report.html").is_file()
    assert evaluation.report_path.is_file()
    assert (evaluation.output_dir / "evaluation.json").is_file()
    assert read_evaluation_json(
        evaluation.output_dir / "evaluation.json"
    ) == evaluation


def test_evaluator_uses_deterministic_final_check(tmp_path: Path) -> None:
    evaluation = asyncio.run(
        evaluate_browser_use_agent(
            agent_factory=lambda task: _Agent(),
            task="Open the product.",
            runs=1,
            output_root=tmp_path,
            final_check=BrowserUseFinalStateCheck(
                url_contains="/product",
                title_contains="Evaluation fixture",
            ),
        )
    )

    assert evaluation.runs[0].status is EvaluationRunStatus.PASSED
    session = read_session_json(
        evaluation.output_dir / "runs/001/session.json"
    )
    assert session.verification_source == "browser-use:deterministic"
    assert session.verification is not None
    judge = session.verification.evidence["browser_use_judge"]
    assert isinstance(judge, dict)
    assert judge["passed"] is True


def test_evaluator_compares_latest_same_task_when_configured(
    tmp_path: Path,
) -> None:
    outcomes = [True, False]
    config = AgentDevToolsConfig(
        compare_previous=True,
        evaluation_directory=tmp_path / "evaluations",
    )

    def factory(task: str) -> _Agent:
        return _Agent(verdict=outcomes.pop(0))

    first = asyncio.run(
        evaluate_browser_use_agent(
            agent_factory=factory,
            task="Open the product.",
            runs=1,
            config=config,
        )
    )
    second = asyncio.run(
        evaluate_browser_use_agent(
            agent_factory=factory,
            task="Open the product.",
            runs=1,
            config=config,
        )
    )

    assert first.comparison_report_path is None
    assert second.comparison_report_path == second.output_dir / "comparison.html"
    comparison = read_evaluation_comparison_json(
        second.output_dir / "comparison.json"
    )
    assert comparison.status.value == "regressed"
    assert "comparison.html" in (
        second.output_dir / "report.html"
    ).read_text(encoding="utf-8")


def test_evaluator_does_not_compare_different_task_text(tmp_path: Path) -> None:
    config = AgentDevToolsConfig(
        compare_previous=True,
        evaluation_directory=tmp_path / "evaluations",
    )

    first = asyncio.run(
        evaluate_browser_use_agent(
            agent_factory=lambda task: _Agent(),
            task="Open the first product.",
            runs=1,
            config=config,
        )
    )
    second = asyncio.run(
        evaluate_browser_use_agent(
            agent_factory=lambda task: _Agent(),
            task="Open the second product.",
            runs=1,
            config=config,
        )
    )

    assert first.comparison_report_path is None
    assert second.comparison_report_path is None


def test_evaluator_preserves_four_distinct_statuses(tmp_path: Path) -> None:
    outcomes: list[object] = [True, False, None, RuntimeError("secret detail")]

    def factory(task: str) -> _Agent:
        outcome = outcomes.pop(0)
        return _Agent(
            verdict=outcome if isinstance(outcome, bool) else None,
            run_error=outcome if isinstance(outcome, Exception) else None,
        )

    evaluation = asyncio.run(
        evaluate_browser_use_agent(
            agent_factory=factory,
            task="Open the product.",
            runs=4,
            output_root=tmp_path,
        )
    )

    assert tuple(run.status for run in evaluation.runs) == (
        EvaluationRunStatus.PASSED,
        EvaluationRunStatus.FAILED,
        EvaluationRunStatus.UNVERIFIED,
        EvaluationRunStatus.ERRORED,
    )
    assert evaluation.completed_run_count == 3
    assert evaluation.empirical_pass_rate == 0.25
    serialized = (evaluation.output_dir / "evaluation.json").read_text(
        encoding="utf-8"
    )
    assert "secret detail" not in serialized
    assert evaluation.runs[3].error_phase == "run"
    assert evaluation.runs[3].error_type == "RuntimeError"


def test_factory_error_creates_trace_and_does_not_stop_later_runs(
    tmp_path: Path,
) -> None:
    attempt = 0

    def factory(task: str) -> _Agent:
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            raise RuntimeError("private factory failure")
        return _Agent()

    evaluation = asyncio.run(
        evaluate_browser_use_agent(
            agent_factory=factory,
            task="Open the product.",
            runs=2,
            output_root=tmp_path,
        )
    )

    assert [run.status for run in evaluation.runs] == [
        EvaluationRunStatus.ERRORED,
        EvaluationRunStatus.PASSED,
    ]
    first_trace = evaluation.output_dir / "runs/001"
    first_session = read_session_json(first_trace / "session.json")
    assert first_session.action_count == 0
    assert "RuntimeError" in (first_session.verification_note or "")
    assert "private factory failure" not in json.dumps(
        json.loads(
            (first_trace / "session.json").read_text(encoding="utf-8")
        )
    )


def test_cleanup_error_marks_run_errored(tmp_path: Path) -> None:
    agent = _Agent(close_error=RuntimeError("secret cleanup message"))

    evaluation = asyncio.run(
        evaluate_browser_use_agent(
            agent_factory=lambda task: agent,
            task="Open the product.",
            runs=1,
            output_root=tmp_path,
        )
    )

    run = evaluation.runs[0]
    assert run.status is EvaluationRunStatus.ERRORED
    assert run.error_phase == "cleanup"
    assert run.error_type == "RuntimeError"
    session_text = (
        evaluation.output_dir / "runs/001/session.json"
    ).read_text(encoding="utf-8")
    assert "secret cleanup message" not in session_text


def test_evaluator_rejects_reused_agent_identity(tmp_path: Path) -> None:
    agent = _Agent()

    evaluation = asyncio.run(
        evaluate_browser_use_agent(
            agent_factory=lambda task: agent,
            task="Open the product.",
            runs=2,
            output_root=tmp_path,
        )
    )

    assert evaluation.runs[0].status is EvaluationRunStatus.PASSED
    assert evaluation.runs[1].status is EvaluationRunStatus.ERRORED
    assert evaluation.runs[1].error_phase == "setup"
    assert evaluation.runs[1].error_type == "_FreshAgentRequiredError"


@pytest.mark.parametrize("field", ["runs", "max_steps"])
@pytest.mark.parametrize("value", [True, 0, -1])
def test_evaluator_rejects_invalid_positive_integer_inputs(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    arguments: dict[str, object] = {
        "agent_factory": lambda task: _Agent(),
        "task": "Open the product.",
        "runs": 1,
        "max_steps": 1,
        "output_root": tmp_path,
    }
    arguments[field] = value

    with pytest.raises(ValueError, match=field):
        asyncio.run(evaluate_browser_use_agent(**arguments))  # type: ignore[arg-type]


def test_evaluator_rejects_unsafe_output_root() -> None:
    with pytest.raises(ValueError, match="root or home"):
        asyncio.run(
            evaluate_browser_use_agent(
                agent_factory=lambda task: _Agent(),
                task="Open the product.",
                runs=1,
                output_root=Path.home(),
            )
        )


def test_evaluator_uses_configured_evaluation_directory(tmp_path: Path) -> None:
    configured_root = tmp_path / "configured-evaluations"
    evaluation = asyncio.run(
        evaluate_browser_use_agent(
            agent_factory=lambda task: _Agent(),
            task="Open the product.",
            runs=1,
            config=AgentDevToolsConfig(evaluation_directory=configured_root),
        )
    )

    assert evaluation.output_dir.parent == configured_root


def test_evaluator_requires_recording_to_be_enabled(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="recording to be enabled"):
        asyncio.run(
            evaluate_browser_use_agent(
                agent_factory=lambda task: _Agent(),
                task="Open the product.",
                runs=1,
                output_root=tmp_path,
                config=AgentDevToolsConfig(enabled=False),
            )
        )
