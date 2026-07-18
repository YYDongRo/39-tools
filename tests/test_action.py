from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_devtools.action import ActionRecord, ActionStatus


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
