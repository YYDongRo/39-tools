import asyncio
from pathlib import Path

import pytest

from agent_devtools import (
    ActionStatus,
    RecordedAsyncTools,
    VerificationResult,
    record_async_tools,
)
from agent_devtools.failure import FailureCategory
from agent_devtools.serialization import read_session_json


class AsyncTools:
    name = "async example"

    def __init__(self) -> None:
        self.value = 0

    async def add(self, amount: int) -> int:
        await asyncio.sleep(0)
        self.value += amount
        return self.value

    async def fail(self, message: str) -> None:
        await asyncio.sleep(0)
        raise RuntimeError(message)

    async def timeout(self) -> None:
        raise TimeoutError("too slow")

    async def cancel(self) -> None:
        raise asyncio.CancelledError

    def inspect(self) -> int:
        return self.value


def test_record_async_tools_awaits_calls_and_records_arguments(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        trace = record_async_tools(AsyncTools(), tmp_path / "trace")

        async with trace as tools:
            result = await tools.add(3)

        assert result == 3
        assert tools.name == "async example"
        assert trace.session.action_count == 1
        action = trace.session.actions[0]
        assert action.action_type == "add"
        assert action.arguments == {"amount": 3}
        assert action.status is ActionStatus.SUCCESS
        assert trace.report_path.is_file()
        assert read_session_json(
            trace.report_path.with_name("session.json")
        ) == trace.session

    asyncio.run(run())


def test_record_async_tools_records_and_reraises_error(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        trace = record_async_tools(AsyncTools(), tmp_path / "trace")

        with pytest.raises(RuntimeError, match="tool failed"):
            async with trace as tools:
                await tools.fail("tool failed")

        action = trace.session.actions[0]
        assert action.status is ActionStatus.FAILURE
        assert action.failure_reason == "RuntimeError: tool failed"
        assert action.failure_category is FailureCategory.OPERATION_ERROR
        assert trace.report_path.is_file()

    asyncio.run(run())


def test_record_async_tools_classifies_timeout(tmp_path: Path) -> None:
    async def run() -> None:
        trace = record_async_tools(AsyncTools(), tmp_path / "trace")

        with pytest.raises(TimeoutError, match="too slow"):
            async with trace as tools:
                await tools.timeout()

        assert (
            trace.session.actions[0].failure_category
            is FailureCategory.TIMEOUT
        )

    asyncio.run(run())


def test_record_async_tools_records_cancellation(tmp_path: Path) -> None:
    async def run() -> None:
        trace = record_async_tools(AsyncTools(), tmp_path / "trace")

        with pytest.raises(asyncio.CancelledError):
            async with trace as tools:
                await tools.cancel()

        action = trace.session.actions[0]
        assert action.status is ActionStatus.FAILURE
        assert action.failure_reason == "CancelledError: "
        assert action.failure_category is FailureCategory.OPERATION_ERROR
        assert trace.report_path.is_file()

    asyncio.run(run())


def test_record_async_tools_accepts_async_callbacks(tmp_path: Path) -> None:
    async def run() -> None:
        raw_tools = AsyncTools()
        screenshot_paths: list[Path] = []

        async def capture_screenshot(path: Path) -> None:
            await asyncio.sleep(0)
            screenshot_paths.append(path)

        async def observe_state() -> dict[str, object]:
            await asyncio.sleep(0)
            return {"value": raw_tools.value}

        trace_dir = tmp_path / "trace"
        trace = record_async_tools(
            raw_tools,
            trace_dir,
            capture_screenshot=capture_screenshot,
            observe_state=observe_state,
        )

        async with trace as tools:
            await tools.add(2)

        assert screenshot_paths == [
            trace_dir / "actions" / "001" / "before.png",
            trace_dir / "actions" / "001" / "after.png",
        ]
        action = trace.session.actions[0]
        assert action.screenshot_before == Path("actions/001/before.png")
        assert action.screenshot_after == Path("actions/001/after.png")
        assert action.observations == {
            "state_before": {"value": 0},
            "state_after": {"value": 2},
            "state_changes": ["value"],
        }

    asyncio.run(run())


def test_record_async_tools_accepts_sync_callbacks(tmp_path: Path) -> None:
    async def run() -> None:
        raw_tools = AsyncTools()
        screenshot_paths: list[Path] = []
        trace = record_async_tools(
            raw_tools,
            tmp_path / "trace",
            capture_screenshot=screenshot_paths.append,
            observe_state=lambda: {"value": raw_tools.value},
        )

        async with trace as tools:
            await tools.add(1)

        assert len(screenshot_paths) == 2
        assert trace.session.actions[0].observations["state_changes"] == [
            "value"
        ]

    asyncio.run(run())


def test_record_async_tools_runs_async_task_verification(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        async def verify() -> VerificationResult:
            await asyncio.sleep(0)
            return VerificationResult(
                expected_state="value is 1",
                observed_state="value is 1",
                passed=True,
            )

        trace = record_async_tools(
            AsyncTools(),
            tmp_path / "trace",
            goal="increase the value",
            task_verification=verify,
        )

        async with trace as tools:
            await tools.add(1)

        assert trace.session.verification is not None
        assert trace.session.verification.passed

    asyncio.run(run())


def test_record_async_tools_rejects_concurrent_actions(
    tmp_path: Path,
) -> None:
    class WaitingTools:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def wait(self, value: int) -> int:
            self.started.set()
            await self.release.wait()
            return value

    async def run() -> None:
        raw_tools = WaitingTools()
        trace = record_async_tools(raw_tools, tmp_path / "trace")

        async with trace as tools:
            first_call = asyncio.create_task(tools.wait(1))
            await raw_tools.started.wait()
            with pytest.raises(
                RuntimeError,
                match="concurrent async tool actions are not supported",
            ):
                await tools.wait(2)
            raw_tools.release.set()
            assert await first_call == 1

        assert trace.session.action_count == 1
        assert trace.session.actions[0].arguments == {"value": 1}

    asyncio.run(run())


def test_record_async_tools_forwards_sync_methods_by_default(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        trace = record_async_tools(AsyncTools(), tmp_path / "trace")

        async with trace as tools:
            assert tools.inspect() == 0
            await tools.add(1)

        assert [action.action_type for action in trace.session.actions] == [
            "add"
        ]

    asyncio.run(run())


def test_record_async_tools_can_explicitly_wrap_sync_method(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        trace = record_async_tools(
            AsyncTools(),
            tmp_path / "trace",
            methods={"inspect"},
        )

        async with trace as tools:
            assert await tools.inspect() == 0  # type: ignore[misc]

        assert trace.session.actions[0].action_type == "inspect"

    asyncio.run(run())


def test_record_async_tools_returns_recorded_async_tools(
    tmp_path: Path,
) -> None:
    assert isinstance(
        record_async_tools(AsyncTools(), tmp_path / "trace"),
        RecordedAsyncTools,
    )
