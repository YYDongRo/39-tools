import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_devtools.action import ActionOutcome, ActionRecord, ActionStatus
from agent_devtools.serialization import (
    read_session_json,
    session_from_dict,
    session_to_dict,
    write_session_json,
)
from agent_devtools.session import ActionSession
from agent_devtools.verification import VerificationResult


def make_action(
    status: ActionStatus,
    failure_reason: str | None = None,
) -> ActionRecord:
    return ActionRecord(
        action_type="click",
        arguments={"selector": "#agent-action"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=125,
        status=status,
        failure_reason=failure_reason,
    )


def test_session_summarizes_actions() -> None:
    session = ActionSession(
        actions=[
            make_action(ActionStatus.SUCCESS),
            make_action(ActionStatus.FAILURE, "target was not found"),
        ]
    )

    assert session.action_count == 2
    assert session.has_failures


def test_empty_session_has_no_failures() -> None:
    session = ActionSession()

    assert session.action_count == 0
    assert not session.has_failures


def test_session_treats_verification_mismatch_as_failure() -> None:
    action = make_action(ActionStatus.SUCCESS)
    action.verification = VerificationResult(
        expected_state="Saved",
        observed_state="Saving",
        passed=False,
        failure_reason="expected 'Saved', observed 'Saving'",
    )

    assert ActionSession(actions=[action]).has_failures


def test_session_with_passed_verification_has_no_failures() -> None:
    action = make_action(ActionStatus.SUCCESS)
    action.verification = VerificationResult(
        expected_state="Saved",
        observed_state="Saved",
        passed=True,
    )

    assert not ActionSession(actions=[action]).has_failures


def test_passed_task_verification_sets_success_after_action_failure() -> None:
    session = ActionSession(
        actions=[make_action(ActionStatus.FAILURE, "first attempt failed")],
        goal="Play a video",
        verification=VerificationResult(
            expected_state="Playing",
            observed_state="Playing",
            passed=True,
        ),
    )

    assert session.outcome is ActionOutcome.SUCCESS
    assert session.has_failures


def test_failed_task_verification_sets_failure() -> None:
    session = ActionSession(
        actions=[make_action(ActionStatus.SUCCESS)],
        goal="Play a video",
        verification=VerificationResult(
            expected_state="Playing",
            observed_state="Paused",
            passed=False,
            failure_reason="expected 'Playing', observed 'Paused'",
        ),
    )

    assert session.outcome is ActionOutcome.FAILURE
    assert session.has_failures


def test_session_without_task_verification_is_unverified() -> None:
    session = ActionSession(
        actions=[make_action(ActionStatus.SUCCESS)],
        goal="Play a video",
    )

    assert session.outcome is ActionOutcome.UNVERIFIED


@pytest.mark.parametrize("goal", ["", "   "])
def test_session_rejects_empty_goal(goal: str) -> None:
    with pytest.raises(ValueError, match="goal cannot be empty"):
        ActionSession(goal=goal)


def test_session_rejects_task_verification_without_goal() -> None:
    with pytest.raises(ValueError, match="task verification requires a goal"):
        ActionSession(
            verification=VerificationResult(
                expected_state="Playing",
                observed_state="Playing",
                passed=True,
            )
        )


def test_session_json_round_trip(tmp_path: Path) -> None:
    session = ActionSession(
        actions=[
            make_action(ActionStatus.SUCCESS),
            make_action(ActionStatus.FAILURE, "target was not found"),
        ]
    )
    output_path = tmp_path / "session.json"

    write_session_json(session, output_path)

    loaded_session = read_session_json(output_path)
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert loaded_session == session
    assert data["schema_version"] == 2
    assert data["goal"] is None
    assert data["verification"] is None
    assert len(data["actions"]) == 2


def test_task_verification_json_round_trip(tmp_path: Path) -> None:
    session = ActionSession(
        actions=[make_action(ActionStatus.SUCCESS)],
        goal="Play a video",
        verification=VerificationResult(
            expected_state="Playing",
            observed_state="Playing",
            passed=True,
            evidence={"selector": "#player-status"},
        ),
    )
    output_path = tmp_path / "session.json"

    write_session_json(session, output_path)

    assert read_session_json(output_path) == session


def test_load_session_schema_version_1_without_task_verification() -> None:
    data = session_to_dict(
        ActionSession(actions=[make_action(ActionStatus.SUCCESS)])
    )
    data["schema_version"] = 1
    del data["goal"]
    del data["verification"]

    session = session_from_dict(data)

    assert session.action_count == 1
    assert session.goal is None
    assert session.verification is None
    assert session.outcome is ActionOutcome.UNVERIFIED


def test_reject_unsupported_session_schema_version() -> None:
    data = session_to_dict(ActionSession())
    data["schema_version"] = 3

    with pytest.raises(ValueError, match="unsupported session schema_version: 3"):
        session_from_dict(data)
