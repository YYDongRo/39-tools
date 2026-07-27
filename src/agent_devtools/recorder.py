from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic_ns

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.failure import classify_exception
from agent_devtools.verification import VerificationResult


def record_action(
    action_type: str,
    arguments: dict[str, object],
    operation: Callable[[], object],
    *,
    screenshot_before: Path | None = None,
    screenshot_after: Path | None = None,
    observations: dict[str, object] | None = None,
    finalize_observations: Callable[[], None] | None = None,
    verification: Callable[[], VerificationResult] | None = None,
) -> ActionRecord:
    start_time = datetime.now(UTC)
    start_ns = monotonic_ns()
    operation_error: Exception | None = None

    try:
        operation()
    except Exception as error:
        operation_error = error

    duration_ms = (monotonic_ns() - start_ns) // 1_000_000
    if finalize_observations is not None:
        try:
            finalize_observations()
        except Exception as error:
            if observations is not None:
                observations["observation_finalizer_error_type"] = type(
                    error
                ).__name__

    if operation_error is not None:
        return ActionRecord(
            action_type=action_type,
            arguments=arguments,
            start_time=start_time,
            duration_ms=duration_ms,
            status=ActionStatus.FAILURE,
            screenshot_before=screenshot_before,
            screenshot_after=screenshot_after,
            failure_reason=(
                f"{type(operation_error).__name__}: {operation_error}"
            ),
            failure_category=classify_exception(operation_error),
            observations=(
                dict(observations) if observations is not None else {}
            ),
        )

    verification_result = None
    if verification is not None:
        verification_result = verification()
        if not isinstance(verification_result, VerificationResult):
            raise TypeError("verification must return a VerificationResult")

    return ActionRecord(
        action_type=action_type,
        arguments=arguments,
        start_time=start_time,
        duration_ms=duration_ms,
        status=ActionStatus.SUCCESS,
        screenshot_before=screenshot_before,
        screenshot_after=screenshot_after,
        observations=dict(observations) if observations is not None else {},
        verification=verification_result,
    )
