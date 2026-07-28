from pathlib import Path

import pytest

from agent_devtools.playwright import observe_playwright_agent


class Agent:
    def run(self, user_request: str, *, tools: object) -> None:
        pass


class MissingRun:
    pass


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
