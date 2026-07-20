from pathlib import Path

import pytest

from agent_devtools.action import ActionStatus
from agent_devtools.serialization import read_session_json
from agent_devtools.session_recorder import SessionRecorder


def test_records_session_with_screenshots_and_persists_each_action(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "trace"
    captured_paths: list[Path] = []

    def capture_screenshot(path: Path) -> None:
        captured_paths.append(path.relative_to(output_dir))
        path.write_bytes(b"fake screenshot")

    recorder = SessionRecorder(output_dir, capture_screenshot)
    success = recorder.record("click", {"selector": "#open"}, lambda: None)

    assert read_session_json(output_dir / "session.json").action_count == 1

    def failing_operation() -> None:
        raise RuntimeError("target was not found")

    failure = recorder.record(
        "click",
        {"selector": "#missing"},
        failing_operation,
    )

    loaded_session = read_session_json(output_dir / "session.json")
    assert success.status is ActionStatus.SUCCESS
    assert failure.status is ActionStatus.FAILURE
    assert loaded_session == recorder.session
    assert loaded_session.action_count == 2
    assert loaded_session.has_failures
    assert captured_paths == [
        Path("actions/001/before.png"),
        Path("actions/001/after.png"),
        Path("actions/002/before.png"),
        Path("actions/002/after.png"),
    ]
    assert (output_dir / "report.html").is_file()


def test_records_session_without_screenshots(tmp_path: Path) -> None:
    recorder = SessionRecorder(tmp_path / "trace")

    action = recorder.record("click", {}, lambda: None)

    assert action.screenshot_before is None
    assert action.screenshot_after is None
    assert not (recorder.output_dir / "actions").exists()
    assert (recorder.output_dir / "session.json").is_file()
    assert (recorder.output_dir / "report.html").is_file()


def test_refuses_to_overwrite_and_resumes_existing_session(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "trace"

    def capture_screenshot(path: Path) -> None:
        path.write_bytes(b"fake screenshot")

    recorder = SessionRecorder(output_dir, capture_screenshot)

    def failing_operation() -> None:
        raise RuntimeError("target was not found")

    recorder.record("click", {"step": 1}, failing_operation)

    with pytest.raises(FileExistsError, match="output directory is not empty"):
        SessionRecorder(output_dir, capture_screenshot)

    resumed = SessionRecorder.resume(output_dir, capture_screenshot)
    resumed.record("click", {"step": 2}, lambda: None)

    loaded_session = read_session_json(output_dir / "session.json")
    assert loaded_session.action_count == 2
    assert loaded_session.has_failures
    assert (output_dir / "actions/001/before.png").is_file()
    assert (output_dir / "actions/002/before.png").is_file()
