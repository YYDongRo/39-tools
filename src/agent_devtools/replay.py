from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.recorder import record_action


__all__ = ["ReplayResult", "replay_click", "replay_fill"]


@dataclass
class ReplayResult:
    source_action: ActionRecord
    replayed_action: ActionRecord
    outcome_matches: bool


def replay_click(
    source_action: ActionRecord,
    execute_click: Callable[[str, int | None], object],
    *,
    screenshot_before: Path | None = None,
    screenshot_after: Path | None = None,
    diagnose_failure: Callable[[ActionRecord], ActionRecord] | None = None,
) -> ReplayResult:
    _validate_replay_arguments(
        source_action,
        action_type="click",
        allowed_arguments={"selector", "timeout_ms"},
    )

    selector = source_action.arguments.get("selector")
    if not isinstance(selector, str) or not selector.strip():
        raise ValueError("click actions require a non-empty selector")

    timeout_ms = _validate_timeout(source_action.arguments)

    arguments: dict[str, object] = {"selector": selector}
    if timeout_ms is not None:
        arguments["timeout_ms"] = timeout_ms

    return _record_replay(
        source_action,
        action_type="click",
        arguments=arguments,
        operation=lambda: execute_click(selector, timeout_ms),
        screenshot_before=screenshot_before,
        screenshot_after=screenshot_after,
        diagnose_failure=diagnose_failure,
    )


def replay_fill(
    source_action: ActionRecord,
    execute_fill: Callable[[str, str, int | None], object],
    *,
    screenshot_before: Path | None = None,
    screenshot_after: Path | None = None,
    diagnose_failure: Callable[[ActionRecord], ActionRecord] | None = None,
) -> ReplayResult:
    """Replay one recorded fill action through a caller-provided executor."""

    _validate_replay_arguments(
        source_action,
        action_type="fill",
        allowed_arguments={"selector", "text", "timeout_ms"},
    )

    selector = source_action.arguments.get("selector")
    if not isinstance(selector, str) or not selector.strip():
        raise ValueError("fill actions require a non-empty selector")

    text = source_action.arguments.get("text")
    if not isinstance(text, str):
        raise ValueError("fill actions require text")

    timeout_ms = _validate_timeout(source_action.arguments)
    arguments: dict[str, object] = {"selector": selector, "text": text}
    if timeout_ms is not None:
        arguments["timeout_ms"] = timeout_ms

    return _record_replay(
        source_action,
        action_type="fill",
        arguments=arguments,
        operation=lambda: execute_fill(selector, text, timeout_ms),
        screenshot_before=screenshot_before,
        screenshot_after=screenshot_after,
        diagnose_failure=diagnose_failure,
    )


def _validate_replay_arguments(
    source_action: ActionRecord,
    *,
    action_type: str,
    allowed_arguments: set[str],
) -> None:
    if source_action.action_type != action_type:
        raise ValueError(f"only {action_type} actions can be replayed")
    if not all(isinstance(key, str) for key in source_action.arguments):
        raise ValueError(f"{action_type} action arguments must use string keys")

    unsupported_arguments = set(source_action.arguments) - allowed_arguments
    if unsupported_arguments:
        names = ", ".join(sorted(unsupported_arguments))
        raise ValueError(f"unsupported {action_type} arguments: {names}")


def _validate_timeout(arguments: dict[str, object]) -> int | None:
    timeout_ms = arguments.get("timeout_ms")
    if timeout_ms is None:
        return None
    if (
        not isinstance(timeout_ms, int)
        or isinstance(timeout_ms, bool)
        or timeout_ms <= 0
    ):
        raise ValueError("timeout_ms must be a positive integer")
    return timeout_ms


def _record_replay(
    source_action: ActionRecord,
    *,
    action_type: str,
    arguments: dict[str, object],
    operation: Callable[[], object],
    screenshot_before: Path | None,
    screenshot_after: Path | None,
    diagnose_failure: Callable[[ActionRecord], ActionRecord] | None,
) -> ReplayResult:
    replayed_action = record_action(
        action_type=action_type,
        arguments=arguments,
        operation=operation,
        screenshot_before=screenshot_before,
        screenshot_after=screenshot_after,
    )
    if (
        replayed_action.status is ActionStatus.FAILURE
        and diagnose_failure is not None
    ):
        replayed_action = diagnose_failure(replayed_action)

    return ReplayResult(
        source_action=source_action,
        replayed_action=replayed_action,
        outcome_matches=_outcome_matches(source_action, replayed_action),
    )


def _outcome_matches(
    source_action: ActionRecord,
    replayed_action: ActionRecord,
) -> bool:
    if source_action.status is not replayed_action.status:
        return False
    if source_action.status is ActionStatus.SUCCESS:
        return True
    if source_action.failure_category is FailureCategory.UNKNOWN:
        return False
    return source_action.failure_category is replayed_action.failure_category
