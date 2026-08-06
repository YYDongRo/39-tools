from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.cli import _browser_use_parser
from agent_devtools.cli import _summary_status, _write_summary
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
            "--summary-json",
            "ci/summary.json",
        ]
    )

    assert parser.prog == "agent-devtools"
    assert args.task == "Open the page."
    assert args.max_steps == 4
    assert args.summary_json.name == "summary.json"


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
        "error_type": None,
    }
