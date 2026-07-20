from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.recorder import record_action


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
) -> ReplayResult:
    if source_action.action_type != "click":
        raise ValueError("only click actions can be replayed")
    if not all(isinstance(key, str) for key in source_action.arguments):
        raise ValueError("click action arguments must use string keys")

    unsupported_arguments = set(source_action.arguments) - {
        "selector",
        "timeout_ms",
    }
    if unsupported_arguments:
        names = ", ".join(sorted(unsupported_arguments))
        raise ValueError(f"unsupported click arguments: {names}")

    selector = source_action.arguments.get("selector")
    if not isinstance(selector, str) or not selector.strip():
        raise ValueError("click actions require a non-empty selector")

    timeout_ms = source_action.arguments.get("timeout_ms")
    if timeout_ms is not None and (
        not isinstance(timeout_ms, int)
        or isinstance(timeout_ms, bool)
        or timeout_ms <= 0
    ):
        raise ValueError("timeout_ms must be a positive integer")

    arguments: dict[str, object] = {"selector": selector}
    if timeout_ms is not None:
        arguments["timeout_ms"] = timeout_ms

    replayed_action = record_action(
        action_type="click",
        arguments=arguments,
        operation=lambda: execute_click(selector, timeout_ms),
        screenshot_before=screenshot_before,
        screenshot_after=screenshot_after,
    )

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
