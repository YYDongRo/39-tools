from datetime import UTC
from pathlib import Path

from pytest import MonkeyPatch

from agent_devtools import recorder
from agent_devtools.action import ActionStatus


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


def test_record_failed_action(monkeypatch: MonkeyPatch) -> None:
    times = iter((2_000_000_000, 2_250_000_000))
    monkeypatch.setattr(recorder, "monotonic_ns", lambda: next(times))

    def operation() -> None:
        raise RuntimeError("target was not found")

    action = recorder.record_action(
        action_type="click",
        arguments={"x": 100, "y": 200},
        operation=operation,
    )

    assert action.status is ActionStatus.FAILURE
    assert action.duration_ms == 250
    assert action.failure_reason == "RuntimeError: target was not found"
