import json
import runpy
from pathlib import Path

from pytest import MonkeyPatch

from agent_devtools.recorder import record_action
from agent_devtools.serialization import write_action_json


def test_example_writes_successful_trace(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    example_path = Path(__file__).parents[1] / "examples" / "record_action.py"

    runpy.run_path(str(example_path), run_name="__main__")

    data = json.loads((tmp_path / "trace/action.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["action_type"] == "click"
    assert data["arguments"] == {"x": 100, "y": 200}
    assert data["status"] == "success"
    assert data["failure_reason"] is None


def test_failed_action_is_written_to_trace(tmp_path: Path) -> None:
    def failing_click() -> None:
        raise RuntimeError("target was not found")

    action = record_action(
        action_type="click",
        arguments={"x": 100, "y": 200},
        operation=failing_click,
    )
    output_path = tmp_path / "trace/action.json"

    write_action_json(action, output_path)

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["status"] == "failure"
    assert data["failure_reason"] == "RuntimeError: target was not found"
    assert data["duration_ms"] >= 0
