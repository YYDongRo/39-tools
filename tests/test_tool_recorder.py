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


def test_record_tools_returns_recorded_tools(
    tmp_path: Path,
) -> None:
    assert isinstance(
        record_tools(ExampleTools(), tmp_path / "trace"),
        RecordedTools,
    )


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
