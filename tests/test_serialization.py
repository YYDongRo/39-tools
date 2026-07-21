import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.serialization import (
    action_from_dict,
    action_to_dict,
    read_action_json,
    write_action_json,
)
from agent_devtools.verification import VerificationResult


def test_convert_successful_action_to_dict() -> None:
    action = ActionRecord(
        action_type="click",
        arguments={"x": 100, "y": 200},
        start_time=datetime(
            2026, 7, 17, 20, 0, tzinfo=timezone(timedelta(hours=8))
        ),
        duration_ms=125,
        status=ActionStatus.SUCCESS,
        screenshot_before=Path("screenshots/before.png"),
        screenshot_after=Path("screenshots/after.png"),
    )

    assert action_to_dict(action) == {
        "schema_version": 4,
        "action_type": "click",
        "arguments": {"x": 100, "y": 200},
        "start_time": "2026-07-17T12:00:00+00:00",
        "duration_ms": 125,
        "status": "success",
        "screenshot_before": "screenshots/before.png",
        "screenshot_after": "screenshots/after.png",
        "failure_reason": None,
        "failure_category": None,
        "failure_evidence": {},
        "verification": None,
    }


def test_convert_failed_action_to_dict() -> None:
    action = ActionRecord(
        action_type="click",
        arguments={},
        start_time=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
        duration_ms=250,
        status=ActionStatus.FAILURE,
        failure_reason="RuntimeError: target was not found",
    )

    data = action_to_dict(action)

    assert data["status"] == "failure"
    assert data["screenshot_before"] is None
    assert data["screenshot_after"] is None
    assert data["failure_reason"] == "RuntimeError: target was not found"
    assert data["failure_category"] == "unknown"
    assert data["failure_evidence"] == {}
    assert data["verification"] is None


def test_write_action_json(tmp_path: Path) -> None:
    action = ActionRecord(
        action_type="输入文本",
        arguments={"text": "你好"},
        start_time=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
        duration_ms=50,
        status=ActionStatus.SUCCESS,
    )
    output_path = tmp_path / "trace" / "action.json"

    write_action_json(action, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert json.loads(content) == action_to_dict(action)
    assert "输入文本" in content
    assert content.endswith("\n")


def test_reject_naive_start_time() -> None:
    action = ActionRecord(
        action_type="click",
        arguments={},
        start_time=datetime(2026, 7, 17, 12, 0),
        duration_ms=125,
        status=ActionStatus.SUCCESS,
    )

    with pytest.raises(ValueError, match="start_time must be timezone-aware"):
        action_to_dict(action)


@pytest.mark.parametrize(
    ("status", "failure_reason"),
    [
        (ActionStatus.SUCCESS, None),
        (ActionStatus.FAILURE, "RuntimeError: target was not found"),
    ],
)
def test_action_json_round_trip(
    tmp_path: Path,
    status: ActionStatus,
    failure_reason: str | None,
) -> None:
    action = ActionRecord(
        action_type="click",
        arguments={"selector": "#agent-action"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=125,
        status=status,
        screenshot_before=Path("before.png"),
        screenshot_after=Path("after.png"),
        failure_reason=failure_reason,
    )
    output_path = tmp_path / "action.json"

    write_action_json(action, output_path)

    assert read_action_json(output_path) == action


def test_reject_unsupported_schema_version() -> None:
    action = ActionRecord(
        action_type="click",
        arguments={},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=125,
        status=ActionStatus.SUCCESS,
    )
    data = action_to_dict(action)
    data["schema_version"] = 5

    with pytest.raises(ValueError, match="unsupported schema_version: 5"):
        action_from_dict(data)


def test_load_schema_version_1_failure_as_unknown_category() -> None:
    action = ActionRecord(
        action_type="click",
        arguments={},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=125,
        status=ActionStatus.FAILURE,
        failure_reason="target was not found",
    )
    data = action_to_dict(action)
    data["schema_version"] = 1
    del data["failure_category"]
    del data["failure_evidence"]
    del data["verification"]

    loaded_action = action_from_dict(data)

    assert loaded_action.failure_category is FailureCategory.UNKNOWN
    assert loaded_action.failure_evidence == {}
    assert loaded_action.verification is None


def test_load_schema_version_2_failure_without_evidence() -> None:
    action = ActionRecord(
        action_type="click",
        arguments={},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=125,
        status=ActionStatus.FAILURE,
        failure_reason="target was not found",
        failure_category=FailureCategory.TARGET_NOT_FOUND,
    )
    data = action_to_dict(action)
    data["schema_version"] = 2
    del data["failure_evidence"]
    del data["verification"]

    loaded_action = action_from_dict(data)

    assert loaded_action.failure_category is FailureCategory.TARGET_NOT_FOUND
    assert loaded_action.failure_evidence == {}
    assert loaded_action.verification is None


def test_load_schema_version_3_without_verification() -> None:
    action = ActionRecord(
        action_type="click",
        arguments={},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=125,
        status=ActionStatus.FAILURE,
        failure_reason="target was not found",
        failure_category=FailureCategory.TARGET_NOT_FOUND,
        failure_evidence={"selector_count": 0},
    )
    data = action_to_dict(action)
    data["schema_version"] = 3
    del data["verification"]

    loaded_action = action_from_dict(data)

    assert loaded_action.failure_category is FailureCategory.TARGET_NOT_FOUND
    assert loaded_action.failure_evidence == {"selector_count": 0}
    assert loaded_action.verification is None


@pytest.mark.parametrize(
    "verification",
    [
        VerificationResult(
            expected_state="Saved",
            observed_state="Saved",
            passed=True,
            evidence={"selector": "#status"},
        ),
        VerificationResult(
            expected_state="Saved",
            observed_state="Saving",
            passed=False,
            evidence={"selector": "#status", "text": "Saving"},
            failure_reason="expected 'Saved', observed 'Saving'",
        ),
    ],
)
def test_action_verification_json_round_trip(
    verification: VerificationResult,
) -> None:
    action = ActionRecord(
        action_type="click",
        arguments={"selector": "#save"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=125,
        status=ActionStatus.SUCCESS,
        verification=verification,
    )

    data = action_to_dict(action)

    assert action_from_dict(data) == action


def test_reject_non_object_verification() -> None:
    action = ActionRecord(
        action_type="click",
        arguments={},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=125,
        status=ActionStatus.SUCCESS,
    )
    data = action_to_dict(action)
    data["verification"] = []

    with pytest.raises(ValueError, match="verification must be an object or null"):
        action_from_dict(data)


def test_reject_invalid_failure_category() -> None:
    action = ActionRecord(
        action_type="click",
        arguments={},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=125,
        status=ActionStatus.FAILURE,
        failure_reason="target was not found",
    )
    data = action_to_dict(action)
    data["failure_category"] = "wrong_target"

    with pytest.raises(
        ValueError,
        match="invalid failure_category: 'wrong_target'",
    ):
        action_from_dict(data)


def test_reject_invalid_failure_evidence() -> None:
    action = ActionRecord(
        action_type="click",
        arguments={},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=125,
        status=ActionStatus.FAILURE,
        failure_reason="target was not found",
    )
    data = action_to_dict(action)
    data["failure_evidence"] = []

    with pytest.raises(
        ValueError,
        match="failure_evidence must be an object with string keys",
    ):
        action_from_dict(data)


def test_reject_non_object_action_json(tmp_path: Path) -> None:
    input_path = tmp_path / "action.json"
    input_path.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="action JSON must contain an object"):
        read_action_json(input_path)


def test_atomic_json_write_preserves_existing_file_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = ActionRecord(
        action_type="click",
        arguments={"step": 1},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=125,
        status=ActionStatus.SUCCESS,
    )
    updated = ActionRecord(
        action_type="click",
        arguments={"step": 2},
        start_time=datetime(2026, 7, 18, 7, 1, tzinfo=UTC),
        duration_ms=250,
        status=ActionStatus.SUCCESS,
    )
    output_path = tmp_path / "action.json"
    write_action_json(original, output_path)

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr("agent_devtools.serialization.os.replace", fail_replace)

    with pytest.raises(OSError, match="simulated replace failure"):
        write_action_json(updated, output_path)

    assert read_action_json(output_path) == original
    assert not any(path.suffix == ".tmp" for path in tmp_path.iterdir())
