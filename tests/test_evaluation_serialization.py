from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_devtools.evaluation import (
    AgentEvaluation,
    DivergenceKind,
    EvaluationRun,
    EvaluationRunStatus,
    FailurePattern,
    TrajectoryDivergence,
)
from agent_devtools.evaluation_serialization import (
    evaluation_from_dict,
    evaluation_to_dict,
    read_evaluation_json,
    write_evaluation_json,
)


NOW = datetime(2026, 8, 1, tzinfo=UTC)


def _evaluation(output_dir: Path) -> AgentEvaluation:
    divergence = TrajectoryDivergence(
        kind=DivergenceKind.ARGUMENTS,
        action_number=2,
        summary="Arguments differed.",
        baseline={"selector": "#correct"},
        observed={"selector": "#wrong"},
    )
    runs = (
        EvaluationRun(
            run_number=1,
            status=EvaluationRunStatus.PASSED,
            started_at=NOW,
            ended_at=NOW + timedelta(seconds=1),
            duration_ms=1000,
            action_count=3,
            trace_directory=Path("runs/001"),
            report_path=Path("runs/001/report.html"),
        ),
        EvaluationRun(
            run_number=2,
            status=EvaluationRunStatus.FAILED,
            started_at=NOW + timedelta(seconds=2),
            ended_at=NOW + timedelta(seconds=4),
            duration_ms=2000,
            action_count=2,
            trace_directory=Path("runs/002"),
            report_path=Path("runs/002/report.html"),
            divergence=divergence,
            issue_code="provider_rate_limited",
        ),
    )
    return AgentEvaluation(
        evaluation_id="stable-example",
        task="Open the correct product.",
        started_at=NOW,
        ended_at=NOW + timedelta(seconds=4),
        requested_run_count=2,
        runs=runs,
        output_dir=output_dir,
        representative_success_run_number=1,
        failure_patterns=(
            FailurePattern(
                pattern_id="pattern-001",
                summary=divergence.summary,
                run_numbers=(2,),
                representative_run_number=2,
                divergence_kind=divergence.kind,
                action_number=2,
                evidence={"observed": divergence.observed},
            ),
        ),
    )


def test_evaluation_json_round_trip(tmp_path: Path) -> None:
    evaluation = _evaluation(tmp_path)
    output_path = tmp_path / "evaluation.json"

    write_evaluation_json(evaluation, output_path)

    assert read_evaluation_json(output_path) == evaluation


def test_evaluation_json_contains_schema_and_derived_summary(
    tmp_path: Path,
) -> None:
    data = evaluation_to_dict(_evaluation(tmp_path))

    assert data["schema_version"] == 1
    assert data["runs"][1]["issue_code"] == "provider_rate_limited"  # type: ignore[index]
    assert data["summary"] == {
        "attempted_run_count": 2,
        "completed_run_count": 2,
        "passed_count": 1,
        "failed_count": 1,
        "unverified_count": 0,
        "errored_count": 0,
        "empirical_pass_rate": 0.5,
        "average_duration_ms": 1500.0,
        "median_duration_ms": 1500.0,
        "average_action_count": 2.5,
        "median_action_count": 2.5,
    }


@pytest.mark.parametrize(
    "unsafe_path",
    ["/tmp/run", "../run", "runs\\001", "C:/Users/example/run"],
)
def test_evaluation_json_rejects_unsafe_stored_paths(
    tmp_path: Path,
    unsafe_path: str,
) -> None:
    data = evaluation_to_dict(_evaluation(tmp_path))
    data["runs"][0]["trace_directory"] = unsafe_path  # type: ignore[index]

    with pytest.raises(ValueError, match="relative path|POSIX"):
        evaluation_from_dict(data, output_dir=tmp_path)


def test_evaluation_json_rejects_tampered_summary(tmp_path: Path) -> None:
    data = evaluation_to_dict(_evaluation(tmp_path))
    data["summary"]["passed_count"] = 2  # type: ignore[index]

    with pytest.raises(ValueError, match="summary"):
        evaluation_from_dict(data, output_dir=tmp_path)
