from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_devtools.action import ActionOutcome, ActionRecord, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.verification import VerificationResult


def test_create_successful_action() -> None:
    action = ActionRecord(
        action_type="click",
        arguments={"x": 100, "y": 200},
        start_time=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
        duration_ms=125,
        status=ActionStatus.SUCCESS,
    )

    assert action.action_type == "click"
    assert action.arguments == {"x": 100, "y": 200}
    assert action.status is ActionStatus.SUCCESS
    assert action.failure_category is None
    assert action.failure_evidence == {}
    assert action.verification is None
    assert action.outcome is ActionOutcome.UNVERIFIED


def test_create_failed_action_with_reason() -> None:
    action = ActionRecord(
        action_type="click",
        arguments={"x": 100, "y": 200},
        start_time=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
        duration_ms=125,
        status=ActionStatus.FAILURE,
        failure_reason="Target was not found",
    )

    assert action.status is ActionStatus.FAILURE
    assert action.failure_reason == "Target was not found"
    assert action.failure_category is FailureCategory.UNKNOWN
    assert action.failure_evidence == {}
    assert action.outcome is ActionOutcome.FAILURE


def test_screenshot_paths_are_optional() -> None:
    action = ActionRecord(
        action_type="click",
        arguments={},
        start_time=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
        duration_ms=125,
        status=ActionStatus.SUCCESS,
    )

    assert action.screenshot_before is None
    assert action.screenshot_after is None


def test_action_can_store_verification_result() -> None:
    verification = VerificationResult(
        expected_state="Saved",
        observed_state="Saving",
        passed=False,
        evidence={"selector": "#status"},
        failure_reason="expected 'Saved', observed 'Saving'",
    )
    action = ActionRecord(
        action_type="click",
        arguments={"selector": "#save"},
        start_time=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
        duration_ms=125,
        status=ActionStatus.SUCCESS,
        verification=verification,
    )

    assert action.status is ActionStatus.SUCCESS
    assert action.verification == verification
    assert action.outcome is ActionOutcome.FAILURE


def test_passed_verification_makes_action_outcome_successful() -> None:
    action = ActionRecord(
        action_type="click",
        arguments={"selector": "#save"},
        start_time=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
        duration_ms=125,
        status=ActionStatus.SUCCESS,
        verification=VerificationResult(
            expected_state="Saved",
            observed_state="Saved",
            passed=True,
        ),
    )

    assert action.outcome is ActionOutcome.SUCCESS


def test_negative_duration_is_invalid() -> None:
    with pytest.raises(ValueError, match="duration_ms cannot be negative"):
        ActionRecord(
            action_type="click",
            arguments={},
            start_time=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
            duration_ms=-1,
            status=ActionStatus.SUCCESS,
        )


def test_failed_action_requires_reason() -> None:
    with pytest.raises(ValueError, match="failed actions require a failure reason"):
        ActionRecord(
            action_type="click",
            arguments={},
            start_time=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
            duration_ms=125,
            status=ActionStatus.FAILURE,
        )


def test_successful_action_rejects_failure_category() -> None:
    with pytest.raises(
        ValueError,
        match="successful actions cannot have a failure category",
    ):
        ActionRecord(
            action_type="click",
            arguments={},
            start_time=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
            duration_ms=125,
            status=ActionStatus.SUCCESS,
            failure_category=FailureCategory.OPERATION_ERROR,
        )


def test_successful_action_rejects_failure_evidence() -> None:
    with pytest.raises(
        ValueError,
        match="successful actions cannot have failure evidence",
    ):
        ActionRecord(
            action_type="click",
            arguments={},
            start_time=datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
            duration_ms=125,
            status=ActionStatus.SUCCESS,
            failure_evidence={"selector_count": 0},
        )
