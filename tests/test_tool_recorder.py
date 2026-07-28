from pathlib import Path

import pytest

from agent_devtools import ActionStatus, RecordedTools, record_tools
from agent_devtools.serialization import read_session_json


class ExampleTools:
    name = "example"

    def add(self, left: int, right: int = 0) -> int:
        return left + right

    def fail(self, message: str) -> None:
        raise RuntimeError(message)

    def inspect(self) -> str:
        return "observed"


class CollidingTools:
    def session(self) -> str:
        return "tool session"

    def report_path(self) -> str:
        return "tool report"


class AsyncTools:
    async def run(self) -> str:
        return "done"


class HiddenAsyncTools:
    async def _run(self) -> str:
        return "done"

    def run(self) -> object:
        return self._run()


def test_record_tools_forwards_calls_and_records_arguments(
    tmp_path: Path,
) -> None:
    trace = record_tools(ExampleTools(), tmp_path / "trace")

    with trace as tools:
        result = tools.add(2, right=3)

    assert result == 5
    assert tools.name == "example"
    assert trace.session.action_count == 1
    assert trace.session.actions[0].action_type == "add"
    assert trace.session.actions[0].arguments == {"left": 2, "right": 3}
    assert trace.session.actions[0].status is ActionStatus.SUCCESS
    assert trace.report_path.is_file()
    assert read_session_json(trace.report_path.with_name("session.json")) == (
        trace.session
    )


def test_record_tools_records_and_reraises_tool_error(tmp_path: Path) -> None:
    trace = record_tools(ExampleTools(), tmp_path / "trace")

    with pytest.raises(RuntimeError, match="tool failed"):
        with trace as tools:
            tools.fail("tool failed")

    action = trace.session.actions[0]
    assert action.status is ActionStatus.FAILURE
    assert action.failure_reason == "RuntimeError: tool failed"
    assert trace.report_path.is_file()


def test_record_tools_can_limit_recorded_methods(tmp_path: Path) -> None:
    trace = record_tools(
        ExampleTools(),
        tmp_path / "trace",
        methods={"add"},
    )

    with trace as tools:
        assert tools.inspect() == "observed"
        assert tools.add(1, 2) == 3

    assert [action.action_type for action in trace.session.actions] == ["add"]


def test_record_tools_uses_optional_screenshot_callback(
    tmp_path: Path,
) -> None:
    screenshot_paths: list[Path] = []
    trace_dir = tmp_path / "trace"
    trace = record_tools(
        ExampleTools(),
        trace_dir,
        capture_screenshot=screenshot_paths.append,
    )

    with trace as tools:
        tools.add(1, 2)

    assert screenshot_paths == [
        trace_dir / "actions" / "001" / "before.png",
        trace_dir / "actions" / "001" / "after.png",
    ]
    assert trace.session.actions[0].screenshot_before == Path(
        "actions/001/before.png"
    )
    assert trace.session.actions[0].screenshot_after == Path(
        "actions/001/after.png"
    )


@pytest.mark.parametrize("methods", ["add", {""}, {1}])
def test_record_tools_rejects_invalid_method_names(
    tmp_path: Path,
    methods: object,
) -> None:
    with pytest.raises(ValueError, match="methods must"):
        record_tools(
            ExampleTools(),
            tmp_path / "trace",
            methods=methods,  # type: ignore[arg-type]
        )


def test_record_tools_rejects_non_callable_observer(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="observe_state must be callable"):
        record_tools(
            ExampleTools(),
            tmp_path / "trace",
            observe_state="state",  # type: ignore[arg-type]
        )


def test_record_tools_returns_recorded_tools(
    tmp_path: Path,
) -> None:
    assert isinstance(
        record_tools(ExampleTools(), tmp_path / "trace"),
        RecordedTools,
    )


def test_record_tools_rejects_async_method(tmp_path: Path) -> None:
    trace = record_tools(AsyncTools(), tmp_path / "trace")

    with pytest.raises(TypeError, match="requires record_async_tools"):
        with trace as tools:
            tools.run()

    assert trace.session.action_count == 0


def test_record_tools_rejects_method_returning_awaitable(
    tmp_path: Path,
) -> None:
    trace = record_tools(HiddenAsyncTools(), tmp_path / "trace")

    with pytest.raises(TypeError, match="requires record_async_tools"):
        with trace as tools:
            tools.run()

    assert trace.session.action_count == 1
    assert trace.session.actions[0].status is ActionStatus.FAILURE


def test_record_tools_accepts_string_output_path(tmp_path: Path) -> None:
    trace = record_tools(ExampleTools(), str(tmp_path / "trace"))

    with trace as tools:
        tools.add(1, 1)

    assert trace.report_path.is_file()


def test_tool_methods_do_not_conflict_with_trace_properties(
    tmp_path: Path,
) -> None:
    trace = record_tools(CollidingTools(), tmp_path / "trace")

    with trace as tools:
        assert tools.session() == "tool session"
        assert tools.report_path() == "tool report"

    assert [action.action_type for action in trace.session.actions] == [
        "session",
        "report_path",
    ]


def test_record_tools_captures_before_after_state_and_changes(
    tmp_path: Path,
) -> None:
    states = iter(
        [
            {
                "url": "https://example.com/start",
                "scroll": {"x": 0, "y": 0},
                "focus": {"id": "search", "tag": "input"},
                "ready": True,
                "removed": "before only",
            },
            {
                "url": "https://example.com/result",
                "scroll": {"x": 0, "y": 100},
                "focus": {"id": "submit", "tag": "button"},
                "ready": True,
                "added": "after only",
            },
        ]
    )
    trace = record_tools(
        ExampleTools(),
        tmp_path / "trace",
        observe_state=lambda: next(states),
    )

    with trace as tools:
        tools.add(1, 2)

    assert trace.session.actions[0].observations == {
        "state_before": {
            "url": "https://example.com/start",
            "scroll": {"x": 0, "y": 0},
            "focus": {"id": "search", "tag": "input"},
            "ready": True,
            "removed": "before only",
        },
        "state_after": {
            "url": "https://example.com/result",
            "scroll": {"x": 0, "y": 100},
            "focus": {"id": "submit", "tag": "button"},
            "ready": True,
            "added": "after only",
        },
        "state_changes": [
            "added",
            "focus",
            "removed",
            "scroll.y",
            "url",
        ],
    }
    assert read_session_json(trace.report_path.with_name("session.json")) == (
        trace.session
    )


def test_record_tools_captures_after_state_when_action_fails(
    tmp_path: Path,
) -> None:
    states = iter(
        [
            {"dialog": "closed"},
            {"dialog": "error"},
        ]
    )
    trace = record_tools(
        ExampleTools(),
        tmp_path / "trace",
        observe_state=lambda: next(states),
    )

    with pytest.raises(RuntimeError, match="tool failed"):
        with trace as tools:
            tools.fail("tool failed")

    action = trace.session.actions[0]
    assert action.status is ActionStatus.FAILURE
    assert action.observations["state_after"] == {"dialog": "error"}
    assert action.observations["state_changes"] == ["dialog"]


def test_observer_error_does_not_prevent_tool_call(tmp_path: Path) -> None:
    call_count = 0

    def observe_state() -> dict[str, object]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("page is changing")
        return {"ready": True}

    trace = record_tools(
        ExampleTools(),
        tmp_path / "trace",
        observe_state=observe_state,
    )

    with trace as tools:
        result = tools.add(1, 2)

    assert result == 3
    assert trace.session.actions[0].status is ActionStatus.SUCCESS
    assert trace.session.actions[0].observations == {
        "state_before_error_type": "RuntimeError",
        "state_after": {"ready": True},
    }


def test_after_observer_error_does_not_hide_tool_failure(
    tmp_path: Path,
) -> None:
    call_count = 0

    def observe_state() -> dict[str, object]:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("page closed")
        return {"ready": True}

    trace = record_tools(
        ExampleTools(),
        tmp_path / "trace",
        observe_state=observe_state,
    )

    with pytest.raises(RuntimeError, match="tool failed"):
        with trace as tools:
            tools.fail("tool failed")

    action = trace.session.actions[0]
    assert action.failure_reason == "RuntimeError: tool failed"
    assert action.observations == {
        "state_before": {"ready": True},
        "state_after_error_type": "RuntimeError",
    }


def test_identical_states_record_no_changed_paths(tmp_path: Path) -> None:
    trace = record_tools(
        ExampleTools(),
        tmp_path / "trace",
        observe_state=lambda: {"ready": True, "scroll": {"y": 0}},
    )

    with trace as tools:
        tools.add(1, 2)

    assert trace.session.actions[0].observations["state_changes"] == []
    assert "No structured state changes detected." in (
        trace.report_path.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    "invalid_state",
    [
        None,
        [],
        {1: "value"},
        {"nested": {1: "value"}},
        {"path": Path("private-state")},
        {"number": float("nan")},
    ],
)
def test_invalid_observer_result_is_recorded_without_failing_action(
    tmp_path: Path,
    invalid_state: object,
) -> None:
    trace = record_tools(
        ExampleTools(),
        tmp_path / "trace",
        observe_state=lambda: invalid_state,  # type: ignore[arg-type,return-value]
    )

    with trace as tools:
        result = tools.add(1, 2)

    assert result == 3
    assert trace.session.actions[0].status is ActionStatus.SUCCESS
    assert trace.session.actions[0].observations == {
        "state_before_error_type": "TypeError",
        "state_after_error_type": "TypeError",
    }
    assert "private-state" not in repr(
        trace.session.actions[0].observations
    )


def test_circular_observer_state_is_recorded_as_type_error(
    tmp_path: Path,
) -> None:
    circular_state: dict[str, object] = {}
    circular_state["self"] = circular_state
    trace = record_tools(
        ExampleTools(),
        tmp_path / "trace",
        observe_state=lambda: circular_state,
    )

    with trace as tools:
        result = tools.add(1, 2)

    assert result == 3
    assert trace.session.actions[0].observations == {
        "state_before_error_type": "TypeError",
        "state_after_error_type": "TypeError",
    }
