from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.replay import replay_click


def make_action(
    *,
    action_type: str = "click",
    arguments: dict[str, object] | None = None,
    status: ActionStatus = ActionStatus.SUCCESS,
    failure_category: FailureCategory | None = None,
) -> ActionRecord:
    return ActionRecord(
        action_type=action_type,
        arguments=(
            arguments if arguments is not None else {"selector": "#agent-action"}
        ),
        start_time=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
        duration_ms=25,
        status=status,
        failure_reason=("original action failed" if status is ActionStatus.FAILURE else None),
        failure_category=failure_category,
    )


def test_replay_successful_click() -> None:
    source_action = make_action()
    calls: list[tuple[str, int | None]] = []

    result = replay_click(
        source_action,
        execute_click=lambda selector, timeout_ms: calls.append(
            (selector, timeout_ms)
        ),
        screenshot_before=Path("before.png"),
        screenshot_after=Path("after.png"),
    )

    assert calls == [("#agent-action", None)]
    assert result.source_action is source_action
    assert result.replayed_action.status is ActionStatus.SUCCESS
    assert result.replayed_action.arguments == {"selector": "#agent-action"}
    assert result.replayed_action.screenshot_before == Path("before.png")
    assert result.replayed_action.screenshot_after == Path("after.png")
    assert result.outcome_matches


def test_replay_matching_timeout_failure() -> None:
    source_action = make_action(
        arguments={"selector": "#missing", "timeout_ms": 100},
        status=ActionStatus.FAILURE,
        failure_category=FailureCategory.TIMEOUT,
    )

    def timeout_click(selector: str, timeout_ms: int | None) -> None:
        raise TimeoutError(f"{selector} timed out after {timeout_ms} ms")

    result = replay_click(source_action, timeout_click)

    assert result.replayed_action.status is ActionStatus.FAILURE
    assert result.replayed_action.failure_category is FailureCategory.TIMEOUT
    assert result.outcome_matches


def test_replay_different_failure_category_does_not_match() -> None:
    source_action = make_action(
        status=ActionStatus.FAILURE,
        failure_category=FailureCategory.TIMEOUT,
    )

    def failing_click(selector: str, timeout_ms: int | None) -> None:
        raise RuntimeError(f"could not click {selector}")

    result = replay_click(source_action, failing_click)

    assert result.replayed_action.failure_category is FailureCategory.OPERATION_ERROR
    assert not result.outcome_matches


def test_replay_unknown_failure_is_not_a_stable_match() -> None:
    source_action = make_action(status=ActionStatus.FAILURE)

    def failing_click(selector: str, timeout_ms: int | None) -> None:
        raise RuntimeError(f"could not click {selector}")

    result = replay_click(source_action, failing_click)

    assert source_action.failure_category is FailureCategory.UNKNOWN
    assert result.replayed_action.failure_category is FailureCategory.OPERATION_ERROR
    assert not result.outcome_matches


@pytest.mark.parametrize(
    ("source_action", "message"),
    [
        (make_action(action_type="fill"), "only click actions can be replayed"),
        (
            make_action(arguments={"selector": ""}),
            "click actions require a non-empty selector",
        ),
        (
            make_action(arguments={}),
            "click actions require a non-empty selector",
        ),
        (
            make_action(arguments={"selector": "#button", "text": "unsafe"}),
            "unsupported click arguments: text",
        ),
        (
            make_action(arguments={"selector": "#button", "timeout_ms": True}),
            "timeout_ms must be a positive integer",
        ),
        (
            make_action(arguments={"selector": "#button", "timeout_ms": 0}),
            "timeout_ms must be a positive integer",
        ),
    ],
)
def test_replay_rejects_unsupported_actions(
    source_action: ActionRecord,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replay_click(source_action, lambda selector, timeout_ms: None)
