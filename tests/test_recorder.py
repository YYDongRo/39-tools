from datetime import UTC
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from agent_devtools import recorder
from agent_devtools.action import ActionOutcome, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.verification import VerificationResult, verify_text_state


def test_record_successful_action(monkeypatch: MonkeyPatch) -> None:
    times = iter((1_000_000_000, 1_125_000_000))
    monkeypatch.setattr(recorder, "monotonic_ns", lambda: next(times))
    operation_was_called = False

    def operation() -> None:
        nonlocal operation_was_called
        operation_was_called = True

    action = recorder.record_action(
        action_type="click",
        arguments={"x": 100, "y": 200},
        operation=operation,
        screenshot_before=Path("screenshots/before.png"),
        screenshot_after=Path("screenshots/after.png"),
    )

    assert operation_was_called
    assert action.status is ActionStatus.SUCCESS
    assert action.start_time.tzinfo is UTC
    assert action.duration_ms == 125
    assert action.screenshot_before == Path("screenshots/before.png")
    assert action.screenshot_after == Path("screenshots/after.png")
    assert action.failure_reason is None
    assert action.failure_category is None


def test_record_failed_action(monkeypatch: MonkeyPatch) -> None:
    times = iter((2_000_000_000, 2_250_000_000))
    monkeypatch.setattr(recorder, "monotonic_ns", lambda: next(times))

    def operation() -> None:
        raise RuntimeError("target was not found")

    verification_was_called = False

    def verification() -> VerificationResult:
        nonlocal verification_was_called
        verification_was_called = True
        return verify_text_state("Saved", "Saved")

    action = recorder.record_action(
        action_type="click",
        arguments={"x": 100, "y": 200},
        operation=operation,
        verification=verification,
    )

    assert action.status is ActionStatus.FAILURE
    assert action.duration_ms == 250
    assert action.failure_reason == "RuntimeError: target was not found"
    assert action.failure_category is FailureCategory.OPERATION_ERROR
    assert not verification_was_called


def test_record_action_runs_verification_after_success(
    monkeypatch: MonkeyPatch,
) -> None:
    times = iter((4_000_000_000, 4_125_000_000))
    monkeypatch.setattr(recorder, "monotonic_ns", lambda: next(times))
    operation_finished = False

    def operation() -> None:
        nonlocal operation_finished
        operation_finished = True

    def verification() -> VerificationResult:
        assert operation_finished
        return verify_text_state("Saved", "Saved")

    action = recorder.record_action(
        action_type="click",
        arguments={"selector": "#save"},
        operation=operation,
        verification=verification,
    )

    assert action.duration_ms == 125
    assert action.verification is not None
    assert action.verification.passed
    assert action.outcome is ActionOutcome.SUCCESS


def test_record_action_preserves_failed_verification() -> None:
    action = recorder.record_action(
        action_type="click",
        arguments={"selector": "#save"},
        operation=lambda: None,
        verification=lambda: verify_text_state("Saved", "Saving"),
    )

    assert action.status is ActionStatus.SUCCESS
    assert action.verification is not None
    assert not action.verification.passed
    assert action.outcome is ActionOutcome.FAILURE


def test_record_action_captures_observations_updated_by_operation() -> None:
    observations: dict[str, object] = {}

    def operation() -> None:
        observations["input_value_after"] = "Agent debugging"

    action = recorder.record_action(
        action_type="fill",
        arguments={"selector": "#search", "text": "Agent debugging"},
        operation=operation,
        observations=observations,
    )

    observations["input_value_after"] = "changed later"

    assert action.observations == {
        "input_value_after": "Agent debugging"
    }
    assert action.outcome is ActionOutcome.UNVERIFIED


def test_record_action_finalizes_observations_after_duration(
    monkeypatch: MonkeyPatch,
) -> None:
    times = iter((5_000_000_000, 5_080_000_000))
    monkeypatch.setattr(recorder, "monotonic_ns", lambda: next(times))
    observations: dict[str, object] = {}
    events: list[str] = []

    def operation() -> None:
        events.append("operation")

    def finalize_observations() -> None:
        events.append("observation")
        observations["state_after"] = {"ready": True}

    def verification() -> VerificationResult:
        events.append("verification")
        return verify_text_state("ready", "ready")

    action = recorder.record_action(
        action_type="click",
        arguments={},
        operation=operation,
        observations=observations,
        finalize_observations=finalize_observations,
        verification=verification,
    )

    assert events == ["operation", "observation", "verification"]
    assert action.duration_ms == 80
    assert action.observations == {"state_after": {"ready": True}}


def test_record_action_finalizes_observations_after_failure() -> None:
    observations: dict[str, object] = {}

    def operation() -> None:
        raise RuntimeError("tool failed")

    action = recorder.record_action(
        action_type="click",
        arguments={},
        operation=operation,
        observations=observations,
        finalize_observations=lambda: observations.update(
            {"state_after": {"dialog_visible": True}}
        ),
    )

    assert action.status is ActionStatus.FAILURE
    assert action.failure_reason == "RuntimeError: tool failed"
    assert action.observations == {
        "state_after": {"dialog_visible": True}
    }


def test_observation_finalizer_error_does_not_change_action_status() -> None:
    observations: dict[str, object] = {}

    def broken_finalizer() -> None:
        raise RuntimeError("observer failed")

    action = recorder.record_action(
        action_type="click",
        arguments={},
        operation=lambda: None,
        observations=observations,
        finalize_observations=broken_finalizer,
    )

    assert action.status is ActionStatus.SUCCESS
    assert action.observations == {
        "observation_finalizer_error_type": "RuntimeError"
    }


def test_record_action_propagates_verification_error() -> None:
    def broken_verification() -> VerificationResult:
        raise RuntimeError("page was already closed")

    with pytest.raises(RuntimeError, match="page was already closed"):
        recorder.record_action(
            action_type="click",
            arguments={},
            operation=lambda: None,
            verification=broken_verification,
        )


def test_record_timeout_action(monkeypatch: MonkeyPatch) -> None:
    times = iter((3_000_000_000, 3_500_000_000))
    monkeypatch.setattr(recorder, "monotonic_ns", lambda: next(times))

    def operation() -> None:
        raise TimeoutError("target did not appear")

    action = recorder.record_action(
        action_type="click",
        arguments={"selector": "#missing"},
        operation=operation,
    )

    assert action.status is ActionStatus.FAILURE
    assert action.duration_ms == 500
    assert action.failure_category is FailureCategory.TIMEOUT
