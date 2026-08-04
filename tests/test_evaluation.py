from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_devtools.evaluation import (
    AgentEvaluation,
    EvaluationRun,
    EvaluationRunStatus,
    FailurePattern,
)


START = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def make_run(
    run_number: int,
    status: EvaluationRunStatus,
    *,
    duration_ms: int = 100,
    action_count: int = 2,
) -> EvaluationRun:
    trace_directory = Path("runs") / f"{run_number:03d}"
    return EvaluationRun(
        run_number=run_number,
        status=status,
        started_at=START + timedelta(seconds=run_number),
        ended_at=START + timedelta(seconds=run_number, milliseconds=duration_ms),
        duration_ms=duration_ms,
        action_count=action_count,
        trace_directory=trace_directory,
        report_path=trace_directory / "report.html",
        error_phase="run" if status is EvaluationRunStatus.ERRORED else None,
        error_type="RuntimeError" if status is EvaluationRunStatus.ERRORED else None,
    )


def test_evaluation_statistics_keep_run_statuses_distinct(tmp_path: Path) -> None:
    runs = (
        make_run(1, EvaluationRunStatus.PASSED, duration_ms=100, action_count=2),
        make_run(2, EvaluationRunStatus.FAILED, duration_ms=200, action_count=4),
        make_run(3, EvaluationRunStatus.UNVERIFIED, duration_ms=300, action_count=6),
        make_run(4, EvaluationRunStatus.ERRORED, duration_ms=50, action_count=0),
    )
    evaluation = AgentEvaluation(
        evaluation_id="evaluation-1",
        task="Open the correct product",
        started_at=START,
        ended_at=START + timedelta(seconds=4),
        requested_run_count=4,
        runs=runs,
        output_dir=tmp_path,
        representative_success_run_number=1,
        failure_patterns=(
            FailurePattern(
                pattern_id="pattern-001",
                summary="The final check failed.",
                run_numbers=(2,),
                representative_run_number=2,
            ),
            FailurePattern(
                pattern_id="pattern-002",
                summary="The final check was unavailable.",
                run_numbers=(3,),
                representative_run_number=3,
            ),
            FailurePattern(
                pattern_id="pattern-003",
                summary="The run raised an error.",
                run_numbers=(4,),
                representative_run_number=4,
            ),
        ),
    )

    assert evaluation.passed_count == 1
    assert evaluation.failed_count == 1
    assert evaluation.unverified_count == 1
    assert evaluation.errored_count == 1
    assert evaluation.completed_run_count == 3
    assert evaluation.empirical_pass_rate == 0.25
    assert evaluation.all_runs_passed is False
    assert evaluation.average_duration_ms == 200
    assert evaluation.median_duration_ms == 200
    assert evaluation.average_action_count == 4
    assert evaluation.median_action_count == 4
    assert evaluation.representative_unsuccessful_run_numbers == (2, 3, 4)


def test_all_runs_passed_is_ci_friendly(tmp_path: Path) -> None:
    evaluation = AgentEvaluation(
        evaluation_id="evaluation-1",
        task="Open the page",
        started_at=START,
        ended_at=START + timedelta(seconds=1),
        requested_run_count=1,
        runs=(make_run(1, EvaluationRunStatus.PASSED),),
        output_dir=tmp_path,
    )

    assert evaluation.all_runs_passed is True
    evaluation.assert_all_passed()


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_evaluation_rejects_invalid_requested_run_count(
    value: object,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        AgentEvaluation(
            evaluation_id="evaluation-1",
            task="Open the page",
            started_at=START,
            ended_at=START,
            requested_run_count=value,  # type: ignore[arg-type]
            runs=(),
            output_dir=tmp_path,
        )


def test_run_requires_safe_relative_report_path() -> None:
    with pytest.raises(ValueError, match="safe relative path"):
        EvaluationRun(
            run_number=1,
            status=EvaluationRunStatus.PASSED,
            started_at=START,
            ended_at=START,
            duration_ms=0,
            action_count=0,
            trace_directory=Path("runs/001"),
            report_path=Path("/tmp/report.html"),
        )


def test_open_report_is_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = tmp_path / "report.html"
    report_path.write_text("report", encoding="utf-8")
    opened: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "agent_devtools.evaluation.webbrowser.open",
        lambda url, *, new: opened.append((url, new)) or True,
    )
    evaluation = AgentEvaluation(
        evaluation_id="evaluation-1",
        task="Open the page",
        started_at=START,
        ended_at=START,
        requested_run_count=1,
        runs=(),
        output_dir=tmp_path,
    )

    assert evaluation.open_report() == report_path.resolve()
    assert opened == [(report_path.resolve().as_uri(), 2)]
