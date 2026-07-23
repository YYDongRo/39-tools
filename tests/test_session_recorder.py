from pathlib import Path

import pytest

from agent_devtools.action import ActionOutcome, ActionStatus
from agent_devtools.serialization import read_session_json
from agent_devtools.session_recorder import SessionRecorder
from agent_devtools.verification import VerificationResult, verify_text_state


def test_records_session_with_screenshots_and_persists_each_action(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "trace"
    captured_paths: list[Path] = []

    def capture_screenshot(path: Path) -> None:
        captured_paths.append(path.relative_to(output_dir))
        path.write_bytes(b"fake screenshot")

    recorder = SessionRecorder(output_dir, capture_screenshot)
    success = recorder.record(
        "click",
        {"selector": "#open"},
        lambda: None,
        observations={"target_visible_after": True},
        verification=lambda: verify_text_state("Open", "Open"),
    )

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
    assert success.outcome is ActionOutcome.SUCCESS
    assert failure.status is ActionStatus.FAILURE
    assert loaded_session == recorder.session
    assert loaded_session.action_count == 2
    assert loaded_session.has_failures
    assert loaded_session.actions[0].verification == success.verification
    assert loaded_session.actions[0].observations == {
        "target_visible_after": True
    }
    assert captured_paths == [
        Path("actions/001/before.png"),
        Path("actions/001/after.png"),
        Path("actions/002/before.png"),
        Path("actions/002/after.png"),
    ]
    assert (output_dir / "report.html").is_file()
    report = (output_dir / "report.html").read_text(encoding="utf-8")
    assert "<dt>Verification status</dt><dd>passed</dd>" in report
    assert "Observations" in report
    assert "&quot;target_visible_after&quot;: true" in report


def test_persists_verification_failure_before_returning(tmp_path: Path) -> None:
    recorder = SessionRecorder(tmp_path / "trace")

    action = recorder.record(
        "click",
        {"selector": "#save"},
        lambda: None,
        verification=lambda: verify_text_state("Saved", "Saving"),
    )

    loaded_action = read_session_json(
        recorder.output_dir / "session.json"
    ).actions[0]
    assert action.outcome is ActionOutcome.FAILURE
    assert loaded_action == action
    assert loaded_action.verification is not None
    assert not loaded_action.verification.passed
    report = (recorder.output_dir / "report.html").read_text(encoding="utf-8")
    assert "<dt>Verification status</dt><dd>failed</dd>" in report


def test_persists_task_verification_and_invalidates_it_on_new_action(
    tmp_path: Path,
) -> None:
    recorder = SessionRecorder(
        tmp_path / "trace",
        goal="Play a video",
    )
    recorder.record("click", {"selector": "#play"}, lambda: None)

    result = recorder.verify_task(
        lambda: verify_text_state("Playing", "Playing")
    )

    loaded_session = read_session_json(recorder.output_dir / "session.json")
    assert result.passed
    assert loaded_session.goal == "Play a video"
    assert loaded_session.verification == result
    assert loaded_session.outcome is ActionOutcome.SUCCESS
    report = (recorder.output_dir / "report.html").read_text(encoding="utf-8")
    assert "Task verification" in report
    assert "task successful" in report

    recorder.record("click", {"selector": "#next"}, lambda: None)

    updated_session = read_session_json(recorder.output_dir / "session.json")
    assert updated_session.verification is None
    assert updated_session.outcome is ActionOutcome.UNVERIFIED


def test_task_verification_requires_session_goal(tmp_path: Path) -> None:
    recorder = SessionRecorder(tmp_path / "trace")

    with pytest.raises(ValueError, match="requires a session goal"):
        recorder.verify_task(lambda: verify_text_state("Ready", "Ready"))


def test_context_manager_automatically_verifies_task(tmp_path: Path) -> None:
    verification_calls = 0

    def verify_task() -> VerificationResult:
        nonlocal verification_calls
        verification_calls += 1
        return verify_text_state("Playing", "Playing")

    with SessionRecorder(
        tmp_path / "trace",
        goal="Play a video",
        task_verification=verify_task,
    ) as recorder:
        recorder.record("click", {"selector": "#play"}, lambda: None)

    loaded_session = read_session_json(recorder.output_dir / "session.json")
    assert verification_calls == 1
    assert loaded_session.verification is not None
    assert loaded_session.verification.passed
    assert loaded_session.outcome is ActionOutcome.SUCCESS


def test_context_manager_skips_task_verification_on_exception(
    tmp_path: Path,
) -> None:
    verification_calls = 0

    def verify_task() -> VerificationResult:
        nonlocal verification_calls
        verification_calls += 1
        return verify_text_state("Playing", "Playing")

    recorder = SessionRecorder(
        tmp_path / "trace",
        goal="Play a video",
        task_verification=verify_task,
    )

    with pytest.raises(RuntimeError, match="agent crashed"):
        with recorder:
            recorder.record("click", {"selector": "#play"}, lambda: None)
            raise RuntimeError("agent crashed")

    loaded_session = read_session_json(recorder.output_dir / "session.json")
    assert verification_calls == 0
    assert loaded_session.verification is None
    assert loaded_session.outcome is ActionOutcome.UNVERIFIED
    assert (recorder.output_dir / "report.html").is_file()


def test_automatic_task_verification_requires_goal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="automatic task verification requires"):
        SessionRecorder(
            tmp_path / "trace",
            task_verification=lambda: verify_text_state("Ready", "Ready"),
        )


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
