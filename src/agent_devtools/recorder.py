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
    verification: Callable[[], VerificationResult] | None = None,
) -> ActionRecord:
    start_time = datetime.now(UTC)
    start_ns = monotonic_ns()

    try:
        operation()
    except Exception as error:
        return ActionRecord(
            action_type=action_type,
            arguments=arguments,
            start_time=start_time,
            duration_ms=(monotonic_ns() - start_ns) // 1_000_000,
            status=ActionStatus.FAILURE,
            screenshot_before=screenshot_before,
            screenshot_after=screenshot_after,
            failure_reason=f"{type(error).__name__}: {error}",
            failure_category=classify_exception(error),
            observations=(
                dict(observations) if observations is not None else {}
            ),
        )

    duration_ms = (monotonic_ns() - start_ns) // 1_000_000
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
