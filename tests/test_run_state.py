from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_devtools.run_state import (
    RunState,
    RunStateStatus,
    read_run_state,
    run_state_from_dict,
    run_state_to_dict,
    write_run_state,
)


STARTED_AT = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def _tracking_state() -> RunState:
    return RunState(
        status=RunStateStatus.TRACKING,
        run_id="run-001",
        task="Open the test page",
        started_at=STARTED_AT,
        updated_at=STARTED_AT + timedelta(seconds=2),
        action_count=1,
    )


def test_run_state_round_trip_uses_versioned_safe_json(tmp_path: Path) -> None:
    state = RunState(
        status=RunStateStatus.FAILED,
        run_id="run-001",
        task="Open the test page",
        started_at=STARTED_AT,
        updated_at=STARTED_AT + timedelta(seconds=3),
        action_count=2,
        report_path=Path("runs/run-001/report.html"),
        issue_code="verification_mismatch",
    )

    output_path = write_run_state(state, tmp_path / "run-state.json")

    assert read_run_state(output_path) == state
    assert run_state_to_dict(state)["schema_version"] == 1
    assert "runs/run-001/report.html" in output_path.read_text(
        encoding="utf-8"
    )


def test_run_state_tracking_requires_active_run_data() -> None:
    with pytest.raises(ValueError, match="run_id and started_at"):
        RunState(
            status=RunStateStatus.TRACKING,
            updated_at=STARTED_AT,
        )


def test_run_state_rejects_naive_or_negative_values() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        RunState(
            status=RunStateStatus.READY,
            updated_at=datetime(2026, 8, 9, 12),
        )

    with pytest.raises(ValueError, match="cannot be negative"):
        RunState(
            status=RunStateStatus.TRACKING,
            run_id="run-001",
            started_at=STARTED_AT,
            updated_at=STARTED_AT,
            action_count=-1,
        )


@pytest.mark.parametrize(
    "value",
    ["/tmp/report.html", "../report.html", "C:/reports/report.html", "runs\\report.html"],
)
def test_run_state_rejects_unsafe_report_paths(value: str) -> None:
    data = run_state_to_dict(
        RunState(
            status=RunStateStatus.PASSED,
            run_id="run-001",
            started_at=STARTED_AT,
            updated_at=STARTED_AT,
            report_path=Path("report.html"),
        )
    )
    data["report_path"] = value

    with pytest.raises(ValueError, match="safe relative path|POSIX"):
        run_state_from_dict(data)


def test_errored_state_stores_only_sanitized_diagnostic() -> None:
    state = RunState(
        status=RunStateStatus.ERRORED,
        run_id="run-001",
        updated_at=STARTED_AT,
        issue_code="provider_credentials",
        error_type="ClientError",
    )

    data = run_state_to_dict(state)

    assert data["issue_code"] == "provider_credentials"
    assert data["error_type"] == "ClientError"
    assert "secret" not in str(data).lower()


def test_run_state_from_dict_rejects_unknown_schema() -> None:
    data = run_state_to_dict(_tracking_state())
    data["schema_version"] = 99

    with pytest.raises(ValueError, match="unsupported run state schema"):
        run_state_from_dict(data)
