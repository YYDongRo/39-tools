from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic_ns

from agent_devtools.action import ActionRecord, ActionStatus


def record_action(
    action_type: str,
    arguments: dict[str, object],
    operation: Callable[[], object],
    *,
    screenshot_before: Path | None = None,
    screenshot_after: Path | None = None,
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
        )

    return ActionRecord(
        action_type=action_type,
        arguments=arguments,
        start_time=start_time,
        duration_ms=(monotonic_ns() - start_ns) // 1_000_000,
        status=ActionStatus.SUCCESS,
        screenshot_before=screenshot_before,
        screenshot_after=screenshot_after,
    )
