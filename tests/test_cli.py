from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import agent_devtools.cli as cli_module
from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.browser_use import (
    BrowserUsePreflightCheck,
    BrowserUsePreflightResult,
)
from agent_devtools.cli import _browser_use_parser
from agent_devtools.cli import (
    _build_evaluation_summary,
    _format_run_summary,
    _format_preflight,
    _summary_status,
    _write_evaluation_summary,
    _write_summary,
)
from agent_devtools.evaluation import (
    AgentEvaluation,
    EvaluationRun,
    EvaluationRunStatus,
)
from agent_devtools.session import ActionSession
from agent_devtools.verification import VerificationResult


def test_installed_cli_parser_uses_stable_command_name() -> None:
    parser = _browser_use_parser()
    args = parser.parse_args(
        [
            "--task",
            "Open the page.",
            "--max-steps",
            "4",
            "--runs",
            "3",
            "--export-bundle",
            "--summary-json",
            "ci/summary.json",
        ]
    )

    assert parser.prog == "agent-devtools"
    assert args.task == "Open the page."
    assert args.max_steps == 4
    assert args.runs == 3
    assert args.export_bundle is True
    assert args.summary_json.name == "summary.json"


def test_installed_cli_parser_accepts_preflight() -> None:
    args = _browser_use_parser().parse_args(["--preflight"])

    assert args.preflight is True


def test_installed_cli_parser_rejects_non_positive_runs() -> None:
    parser = _browser_use_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--runs", "0"])


def _session_with_verification(passed: bool) -> ActionSession:
    return ActionSession(
        goal="Open the page.",
        actions=[
            ActionRecord(
                action_type="navigate",
                arguments={"url": "https://example.test"},
                start_time=datetime(2026, 1, 1, tzinfo=UTC),
                duration_ms=10,
                status=ActionStatus.SUCCESS,
            )
        ],
        verification=VerificationResult(
            expected_state="the page is open",
            observed_state="the page is open" if passed else "another page is open",
            passed=passed,
            failure_reason=None if passed else "the wrong page is open",
        ),
    )


def test_summary_status_distinguishes_final_verification_and_errors() -> None:
    assert _summary_status(_session_with_verification(True)) == "passed"
    assert _summary_status(_session_with_verification(False)) == "failed"
    assert _summary_status(ActionSession(goal="Open the page.")) == "unverified"
    assert (
        _summary_status(
            _session_with_verification(True),
            run_error=RuntimeError("not persisted"),
        )
        == "errored"
    )


def test_summary_status_marks_zero_action_success_unverified_in_strict_mode() -> None:
    session = ActionSession(
        goal="Complete the task",
        verification=VerificationResult(
            expected_state="done",
            observed_state="done",
            passed=True,
        ),
    )

    assert (
        _summary_status(session, require_recorded_actions=True)
        == "unverified"
    )
    assert (
        _summary_status(
            _session_with_verification(True),
            require_recorded_actions=True,
        )
        == "passed"
    )


def test_run_summary_explains_strict_zero_action_coverage(tmp_path: Path) -> None:
    session = ActionSession(
        goal="Complete the task",
        verification=VerificationResult(
            expected_state="done",
            observed_state="done",
            passed=True,
        ),
    )

    summary = _format_run_summary(
        session,
        tmp_path / "report.html",
        require_recorded_actions=True,
    )

    assert "Result: UNVERIFIED" in summary
    assert "no browser actions captured" in summary


def test_run_summary_is_concise_and_explains_final_failure(tmp_path: Path) -> None:
    summary = _format_run_summary(
        _session_with_verification(False),
        tmp_path / "report.html",
    )

    assert summary.count("Report:") == 1
    assert "Result: FAIL" in summary
    assert "Actions: 1 succeeded, 0 failed" in summary
    assert "Final check: failed" in summary
    assert "Reason: the wrong page is open" in summary
    assert "Task result:" not in summary


def test_run_summary_explains_provider_rate_limit(tmp_path: Path) -> None:
    session = ActionSession(
        goal="Open the requested page.",
        verification_source="browser-use",
        verification_note=(
            "Browser Use model provider rate-limited the run. "
            "Check provider quota and retry policy."
        ),
    )

    summary = _format_run_summary(session, tmp_path / "report.html")

    assert "Result: UNVERIFIED" in summary
    assert "Issue: Provider rate limit reached" in summary
    assert "Next: Wait for quota recovery" in summary
    assert "Reason:" not in summary


def test_preflight_summary_is_short_and_explicit() -> None:
    summary = _format_preflight(
        BrowserUsePreflightResult(
            checks=(
                BrowserUsePreflightCheck(
                    name="recording hook",
                    passed=True,
                    detail="model actions will enter the recorder",
                ),
                BrowserUsePreflightCheck(
                    name="trace directory",
                    passed=False,
                    detail="trace directory is not writable (PermissionError)",
                ),
            )
        )
    )

    assert "Agent DevTools preflight" in summary
    assert "Result: FAIL" in summary
    assert "[PASS] recording hook" in summary
    assert "[FAIL] trace directory" in summary


def test_summary_json_is_short_versioned_and_uses_relative_report_paths(
    tmp_path: Path,
) -> None:
    summary_path = tmp_path / "ci" / "summary.json"
    report_path = Path.cwd() / "trace" / "report.html"

    _write_summary(
        summary_path,
        status="passed",
        report_path=report_path,
        session=_session_with_verification(True),
    )

    data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert data == {
        "schema_version": 1,
        "status": "passed",
        "action_count": 1,
        "action_success_count": 1,
        "action_failure_count": 0,
        "final_check": "passed",
        "report_path": "trace/report.html",
        "session_path": "trace/session.json",
        "issue_code": None,
        "issue_title": None,
        "issue_next_step": None,
        "error_type": None,
    }


def test_summary_json_includes_structured_provider_issue(tmp_path: Path) -> None:
    data = cli_module._build_summary(
        status="unverified",
        report_path=tmp_path / "report.html",
        session=ActionSession(
            goal="Open the requested page.",
            verification_source="browser-use",
            issue_code="provider_rate_limited",
        ),
    )

    assert data["issue_code"] == "provider_rate_limited"
    assert data["issue_title"] == "Provider rate limit reached"
    assert data["issue_next_step"] == (
        "Wait for quota recovery, then retry the task."
    )


def _evaluation_for_cli_summary(
    *,
    issue_code: str | None = None,
) -> AgentEvaluation:
    started_at = datetime(2026, 1, 1, tzinfo=UTC)
    run = EvaluationRun(
        run_number=1,
        status=EvaluationRunStatus.FAILED,
        started_at=started_at,
        ended_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        duration_ms=1000,
        action_count=2,
        trace_directory=Path("runs/001"),
        report_path=Path("runs/001/report.html"),
        issue_code=issue_code,
    )
    return AgentEvaluation(
        evaluation_id="cli-summary",
        task="Open the page.",
        started_at=started_at,
        ended_at=datetime(2026, 1, 1, 0, 0, 2, tzinfo=UTC),
        requested_run_count=1,
        runs=(run,),
        output_dir=Path("evaluations/cli-summary"),
    )


def test_evaluation_summary_preserves_counts_and_report_paths(
    tmp_path: Path,
) -> None:
    evaluation = _evaluation_for_cli_summary()
    summary_path = tmp_path / "evaluation-summary.json"

    _write_evaluation_summary(summary_path, evaluation)
    data = json.loads(summary_path.read_text(encoding="utf-8"))

    assert data == _build_evaluation_summary(evaluation)
    assert data["kind"] == "evaluation"
    assert data["status"] == "failed"
    assert data["failed_count"] == 1
    assert data["report_path"] == "evaluations/cli-summary/report.html"
    assert data["evaluation_path"] == "evaluations/cli-summary/evaluation.json"
    assert data["comparison_path"] is None


def test_evaluation_summary_includes_issue_code_counts() -> None:
    evaluation = _evaluation_for_cli_summary(
        issue_code="provider_rate_limited",
    )

    summary = _build_evaluation_summary(evaluation)

    assert summary["issue_code_counts"] == {"provider_rate_limited": 1}


def test_cli_repeated_runs_use_fresh_agents_and_evaluation_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "agent_devtools.toml"
    config_path.write_text(
        "[agent_devtools]\nenabled = true\nopen_report = false\n",
        encoding="utf-8",
    )
    summary_path = tmp_path / "summary.json"
    created_agents: list[object] = []
    captured: dict[str, object] = {}

    class FakeBrowser:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeAgent:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    async def fake_evaluate(**kwargs: object) -> AgentEvaluation:
        captured.update(kwargs)
        factory = kwargs["agent_factory"]
        assert callable(factory)
        task = kwargs["task"]
        assert isinstance(task, str)
        for _ in range(2):
            created_agents.append(factory(task))  # type: ignore[operator]
        return _evaluation_for_cli_summary()

    monkeypatch.setattr(cli_module, "_resolve_provider", lambda requested: "openai")
    monkeypatch.setattr(cli_module, "_create_llm", lambda provider, model: object())
    monkeypatch.setattr(cli_module, "evaluate_browser_use_agent", fake_evaluate)
    monkeypatch.setitem(
        sys.modules,
        "browser_use",
        SimpleNamespace(Agent=FakeAgent, Browser=FakeBrowser),
    )

    result = asyncio.run(
        cli_module._browser_use_main(
            [
                "--config",
                str(config_path),
                "--task",
                "Open the page.",
                "--runs",
                "2",
                "--summary-json",
                str(summary_path),
            ]
        )
    )

    assert result == 1
    assert len(created_agents) == 2
    assert created_agents[0] is not created_agents[1]
    assert captured["runs"] == 2
    assert captured["task"] == "Open the page."
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["kind"] == "evaluation"


def test_cli_single_run_prints_one_concise_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "agent_devtools.toml"
    config_path.write_text(
        "[agent_devtools]\nenabled = true\nopen_report = false\n",
        encoding="utf-8",
    )
    captured: dict[str, object] = {}

    class FakeBrowser:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        async def stop(self) -> None:
            return None

    class FakeAgent:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeObservedAgent:
        last_report_path = tmp_path / "trace" / "report.html"
        last_session = _session_with_verification(True)

        async def run(self, **kwargs: object) -> None:
            return None

        def assert_last_task_passed(self) -> None:
            return None

    def fake_observe(*args: object, **kwargs: object) -> FakeObservedAgent:
        captured.update(kwargs)
        return FakeObservedAgent()

    monkeypatch.setattr(cli_module, "_resolve_provider", lambda requested: "openai")
    monkeypatch.setattr(cli_module, "_create_llm", lambda provider, model: object())
    monkeypatch.setattr(cli_module, "observe_browser_use_agent", fake_observe)
    monkeypatch.setitem(
        sys.modules,
        "browser_use",
        SimpleNamespace(Agent=FakeAgent, Browser=FakeBrowser),
    )

    result = asyncio.run(
        cli_module._browser_use_main(
            [
                "--config",
                str(config_path),
                "--task",
                "Open the page.",
            ]
        )
    )

    output = capsys.readouterr().out
    assert result == 0
    assert captured["print_summary"] is False
    assert output.count("Report:") == 1
    assert output.count("Result: PASS") == 1
    assert "Task result:" not in output


def test_cli_preflight_exits_without_running_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "agent_devtools.toml"
    config_path.write_text(
        "[agent_devtools]\nenabled = true\nopen_report = false\n",
        encoding="utf-8",
    )
    calls: list[str] = []

    class FakeBrowser:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        async def stop(self) -> None:
            calls.append("browser.stop")

    class FakeAgent:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeObservedAgent:
        def preflight(self) -> BrowserUsePreflightResult:
            calls.append("preflight")
            return BrowserUsePreflightResult(
                checks=(
                    BrowserUsePreflightCheck(
                        name="recording hook",
                        passed=True,
                        detail="model actions will enter the recorder",
                    ),
                )
            )

        async def run(self, **kwargs: object) -> None:
            calls.append("run")

    monkeypatch.setattr(cli_module, "_resolve_provider", lambda requested: "openai")
    monkeypatch.setattr(cli_module, "_create_llm", lambda provider, model: object())
    monkeypatch.setattr(
        cli_module,
        "observe_browser_use_agent",
        lambda *args, **kwargs: FakeObservedAgent(),
    )
    monkeypatch.setitem(
        sys.modules,
        "browser_use",
        SimpleNamespace(Agent=FakeAgent, Browser=FakeBrowser),
    )

    result = asyncio.run(
        cli_module._browser_use_main(
            [
                "--config",
                str(config_path),
                "--task",
                "Complete the task.",
                "--preflight",
            ]
        )
    )

    output = capsys.readouterr().out
    assert result == 0
    assert calls == ["preflight", "browser.stop"]
    assert "Result: PASS" in output


def test_cli_strict_coverage_returns_nonzero_for_zero_action_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "agent_devtools.toml"
    config_path.write_text(
        "[agent_devtools]\n"
        "enabled = true\n"
        "require_recorded_actions = true\n"
        "open_report = false\n",
        encoding="utf-8",
    )

    class FakeBrowser:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        async def stop(self) -> None:
            return None

    class FakeAgent:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeObservedAgent:
        last_report_path = tmp_path / "trace" / "report.html"
        last_session = ActionSession(
            goal="Complete the task.",
            verification=VerificationResult(
                expected_state="done",
                observed_state="done",
                passed=True,
            ),
        )

        async def run(self, **kwargs: object) -> None:
            return None

        def assert_last_task_passed(self) -> None:
            raise AssertionError("no browser actions captured")

    monkeypatch.setattr(cli_module, "_resolve_provider", lambda requested: "openai")
    monkeypatch.setattr(cli_module, "_create_llm", lambda provider, model: object())
    monkeypatch.setattr(
        cli_module,
        "observe_browser_use_agent",
        lambda *args, **kwargs: FakeObservedAgent(),
    )
    monkeypatch.setitem(
        sys.modules,
        "browser_use",
        SimpleNamespace(Agent=FakeAgent, Browser=FakeBrowser),
    )

    result = asyncio.run(
        cli_module._browser_use_main(
            [
                "--config",
                str(config_path),
                "--task",
                "Complete the task.",
            ]
        )
    )

    output = capsys.readouterr().out
    assert result == 1
    assert "Result: UNVERIFIED" in output
    assert "no browser actions captured" in output
