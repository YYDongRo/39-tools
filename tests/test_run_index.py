from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.evaluation import (
    AgentEvaluation,
    EvaluationRun,
    EvaluationRunStatus,
)
from agent_devtools.evaluation_serialization import write_evaluation_json
from agent_devtools.report import write_session_html
from agent_devtools.run_index import write_run_index
from agent_devtools.serialization import write_session_json
from agent_devtools.session import ActionSession
from agent_devtools.verification import VerificationResult


def _session(goal: str, started_at: datetime, *, passed: bool) -> ActionSession:
    return ActionSession(
        goal=goal,
        actions=[
            ActionRecord(
                action_type="navigate",
                arguments={"url": "https://example.test"},
                start_time=started_at,
                duration_ms=25,
                status=ActionStatus.SUCCESS,
            )
        ],
        verification=VerificationResult(
            expected_state="the requested page is open",
            observed_state=(
                "the requested page is open"
                if passed
                else "a different page is open"
            ),
            passed=passed,
            failure_reason=None if passed else "the wrong page is open",
        ),
    )


def _write_session_trace(root: Path, name: str, session: ActionSession) -> None:
    trace = root / name
    trace.mkdir(parents=True)
    write_session_json(session, trace / "session.json")
    write_session_html(session, trace / "report.html")


def test_write_run_index_lists_reports_and_bundles(tmp_path: Path) -> None:
    root = tmp_path / "trace"
    _write_session_trace(
        root,
        "20260809T120000Z-success",
        _session(
            "Open the requested page",
            datetime(2026, 8, 9, 12, tzinfo=UTC),
            passed=True,
        ),
    )
    _write_session_trace(
        root,
        "20260810T120000Z-failure",
        _session(
            "Open the <requested> page",
            datetime(2026, 8, 10, 12, tzinfo=UTC),
            passed=False,
        ),
    )
    bundles = root / "bundles"
    bundles.mkdir()
    (bundles / "agent-devtools-20260810-test001.zip").write_bytes(b"zip")

    index_path = write_run_index(root)
    first = index_path.read_text(encoding="utf-8")
    second = write_run_index(root).read_text(encoding="utf-8")

    assert index_path == root / "index.html"
    assert first == second
    assert "Recent runs" in first
    assert "Failed" in first
    assert "&lt;requested&gt;" in first
    assert 'href="20260810T120000Z-failure/report.html"' in first
    assert 'href="20260809T120000Z-success/report.html"' in first
    assert (
        'href="bundles/agent-devtools-20260810-test001.zip"' in first
    )
    assert str(root) not in first
    assert first.index("20260810T120000Z-failure/report.html") < first.index(
        "20260809T120000Z-success/report.html"
    )


def test_write_run_index_includes_stability_evaluations(tmp_path: Path) -> None:
    root = tmp_path / "evaluations"
    evaluation_dir = root / "20260810T120000Z-evaluation"
    evaluation_dir.mkdir(parents=True)
    (evaluation_dir / "report.html").write_text(
        "<html><body>evaluation</body></html>",
        encoding="utf-8",
    )
    started_at = datetime(2026, 8, 10, 12, tzinfo=UTC)
    run = EvaluationRun(
        run_number=1,
        status=EvaluationRunStatus.PASSED,
        started_at=started_at,
        ended_at=datetime(2026, 8, 10, 12, 0, 1, tzinfo=UTC),
        duration_ms=1000,
        action_count=2,
        trace_directory=Path("runs/001"),
        report_path=Path("runs/001/report.html"),
    )
    evaluation = AgentEvaluation(
        evaluation_id="evaluation-1",
        task="Open the requested page",
        started_at=started_at,
        ended_at=datetime(2026, 8, 10, 12, 0, 1, tzinfo=UTC),
        requested_run_count=1,
        runs=(run,),
        output_dir=evaluation_dir,
        representative_success_run_number=1,
    )
    write_evaluation_json(evaluation, evaluation_dir / "evaluation.json")

    html = write_run_index(root).read_text(encoding="utf-8")

    assert "Stability evaluation" in html
    assert "1 passed, 0 failed, 0 unverified, 0 errored" in html
    assert 'href="20260810T120000Z-evaluation/report.html"' in html
