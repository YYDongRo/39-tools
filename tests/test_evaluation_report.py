from datetime import UTC, datetime
from pathlib import Path

from agent_devtools.evaluation import (
    AgentEvaluation,
    DivergenceKind,
    EvaluationRun,
    EvaluationRunStatus,
    FailurePattern,
    TrajectoryDivergence,
)
from agent_devtools.evaluation_report import render_evaluation_html


NOW = datetime(2026, 8, 1, tzinfo=UTC)


def _run(
    number: int,
    status: EvaluationRunStatus,
    divergence: TrajectoryDivergence | None = None,
) -> EvaluationRun:
    return EvaluationRun(
        run_number=number,
        status=status,
        started_at=NOW,
        ended_at=NOW,
        duration_ms=number * 100,
        action_count=number,
        trace_directory=Path(f"runs/{number:03d}"),
        report_path=Path(f"runs/{number:03d}/report.html"),
        divergence=divergence,
    )


def test_report_shows_statuses_links_baseline_and_repeated_pattern(
    tmp_path: Path,
) -> None:
    divergence = TrajectoryDivergence(
        kind=DivergenceKind.ARGUMENTS,
        action_number=2,
        summary="Wrong target selected.",
    )
    runs = (
        _run(1, EvaluationRunStatus.PASSED),
        _run(2, EvaluationRunStatus.FAILED, divergence),
        _run(3, EvaluationRunStatus.FAILED, divergence),
    )
    evaluation = AgentEvaluation(
        evaluation_id="report-test",
        task="Open <the> product.",
        started_at=NOW,
        ended_at=NOW,
        requested_run_count=3,
        runs=runs,
        output_dir=tmp_path,
        representative_success_run_number=1,
        failure_patterns=(
            FailurePattern(
                pattern_id="pattern-001",
                summary="Wrong target selected.",
                run_numbers=(2, 3),
                representative_run_number=2,
                divergence_kind=DivergenceKind.ARGUMENTS,
                action_number=2,
            ),
        ),
    )

    html = render_evaluation_html(evaluation)

    assert "Open &lt;the&gt; product." in html
    assert "Passed: 1" in html
    assert "Failed: 2" in html
    assert "33.3%" in html
    assert "Average duration" in html
    assert "Median duration" in html
    assert "Average actions" in html
    assert "Median actions" in html
    assert 'href="runs/001/report.html"' in html
    assert 'href="runs/002/report.html"' in html
    assert "Runs 2, 3" in html
    assert "does not prove the agent's true reliability" in html


def test_report_explains_missing_success_baseline(tmp_path: Path) -> None:
    evaluation = AgentEvaluation(
        evaluation_id="no-baseline",
        task="Open the product.",
        started_at=NOW,
        ended_at=NOW,
        requested_run_count=1,
        runs=(_run(1, EvaluationRunStatus.UNVERIFIED),),
        output_dir=tmp_path,
    )

    html = render_evaluation_html(evaluation)

    assert "No successful baseline was available" in html
    assert "Unverified: 1" in html
