from datetime import UTC, datetime, timedelta
from pathlib import Path

from agent_devtools.evaluation import (
    AgentEvaluation,
    DivergenceKind,
    EvaluationComparisonStatus,
    EvaluationRun,
    EvaluationRunStatus,
    FailurePattern,
)
from agent_devtools.evaluation_comparison import compare_evaluations
from agent_devtools.evaluation_comparison_report import (
    render_evaluation_comparison_html,
)
from agent_devtools.evaluation_comparison_serialization import (
    read_evaluation_comparison_json,
    write_evaluation_comparison_json,
)


NOW = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
TASK = "Open the correct product."


def _evaluation(
    output_dir: Path,
    evaluation_id: str,
    statuses: tuple[EvaluationRunStatus, ...],
    *,
    task: str = TASK,
    pattern: FailurePattern | None = None,
) -> AgentEvaluation:
    runs = tuple(
        EvaluationRun(
            run_number=number,
            status=status,
            started_at=NOW + timedelta(seconds=number),
            ended_at=NOW + timedelta(seconds=number, milliseconds=100),
            duration_ms=100,
            action_count=2,
            trace_directory=Path("runs") / f"{number:03d}",
            report_path=Path("runs") / f"{number:03d}" / "report.html",
        )
        for number, status in enumerate(statuses, start=1)
    )
    patterns = (pattern,) if pattern is not None else ()
    return AgentEvaluation(
        evaluation_id=evaluation_id,
        task=task,
        started_at=NOW,
        ended_at=NOW + timedelta(seconds=10),
        requested_run_count=len(statuses),
        runs=runs,
        output_dir=output_dir,
        representative_success_run_number=(
            next(
                (
                    run.run_number
                    for run in runs
                    if run.status is EvaluationRunStatus.PASSED
                ),
                None,
            )
        ),
        failure_patterns=patterns,
    )


def _pattern(
    *,
    pattern_id: str = "pattern-001",
    run_numbers: tuple[int, ...] = (2,),
) -> FailurePattern:
    return FailurePattern(
        pattern_id=pattern_id,
        summary="The wrong product was selected.",
        run_numbers=run_numbers,
        representative_run_number=run_numbers[0],
        divergence_kind=DivergenceKind.ARGUMENTS,
        action_number=2,
        evidence={"target": "wrong-product"},
    )


def test_comparison_detects_improvement_and_resolved_pattern(tmp_path: Path) -> None:
    baseline = _evaluation(
        tmp_path / "before",
        "before",
        (EvaluationRunStatus.PASSED, EvaluationRunStatus.FAILED),
        pattern=_pattern(),
    )
    current = _evaluation(
        tmp_path / "after",
        "after",
        (EvaluationRunStatus.PASSED, EvaluationRunStatus.PASSED),
    )

    comparison = compare_evaluations(baseline, current)

    assert comparison.status is EvaluationComparisonStatus.IMPROVED
    assert comparison.pass_rate_delta == 0.5
    assert comparison.new_patterns == ()
    assert [pattern.summary for pattern in comparison.resolved_patterns] == [
        "The wrong product was selected."
    ]


def test_comparison_detects_regression_and_new_pattern(tmp_path: Path) -> None:
    baseline = _evaluation(
        tmp_path / "before",
        "before",
        (EvaluationRunStatus.PASSED, EvaluationRunStatus.PASSED),
    )
    current = _evaluation(
        tmp_path / "after",
        "after",
        (EvaluationRunStatus.PASSED, EvaluationRunStatus.FAILED),
        pattern=_pattern(),
    )

    comparison = compare_evaluations(baseline, current)

    assert comparison.status is EvaluationComparisonStatus.REGRESSED
    assert len(comparison.new_patterns) == 1


def test_comparison_matches_pattern_content_not_generated_id(
    tmp_path: Path,
) -> None:
    baseline = _evaluation(
        tmp_path / "before",
        "before",
        (EvaluationRunStatus.PASSED, EvaluationRunStatus.FAILED),
        pattern=_pattern(pattern_id="pattern-001"),
    )
    current = _evaluation(
        tmp_path / "after",
        "after",
        (EvaluationRunStatus.PASSED, EvaluationRunStatus.FAILED),
        pattern=_pattern(pattern_id="pattern-009"),
    )

    comparison = compare_evaluations(baseline, current)

    assert comparison.status is EvaluationComparisonStatus.UNCHANGED
    assert comparison.new_patterns == ()
    assert comparison.resolved_patterns == ()


def test_comparison_marks_changed_tasks_incomparable(tmp_path: Path) -> None:
    baseline = _evaluation(
        tmp_path / "before",
        "before",
        (EvaluationRunStatus.PASSED,),
    )
    current = _evaluation(
        tmp_path / "after",
        "after",
        (EvaluationRunStatus.PASSED,),
        task="Open a different product.",
    )

    comparison = compare_evaluations(baseline, current)

    assert comparison.status is EvaluationComparisonStatus.INCOMPARABLE
    assert comparison.reason is not None
    assert comparison.new_patterns == ()


def test_comparison_json_round_trip_and_report_links(tmp_path: Path) -> None:
    baseline = _evaluation(
        tmp_path / "before",
        "before",
        (EvaluationRunStatus.PASSED, EvaluationRunStatus.PASSED),
    )
    current = _evaluation(
        tmp_path / "after",
        "after",
        (EvaluationRunStatus.PASSED, EvaluationRunStatus.FAILED),
        pattern=_pattern(),
    )
    comparison = compare_evaluations(baseline, current)
    output_path = tmp_path / "comparison.json"

    write_evaluation_comparison_json(comparison, output_path)

    assert read_evaluation_comparison_json(output_path) == comparison
    html = render_evaluation_comparison_html(
        comparison,
        baseline_report_href="../before/report.html",
        current_report_href="report.html",
    )
    assert "Regressed" in html
    assert 'href="../before/report.html"' in html
    assert 'href="report.html"' in html
    assert "The wrong product was selected." in html
