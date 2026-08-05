import runpy
from pathlib import Path

from agent_devtools import ActionStatus
from agent_devtools.serialization import read_session_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_SCRIPT = runpy.run_path(str(PROJECT_ROOT / "examples" / "generic_agent.py"))
run_demo = DEMO_SCRIPT["run_demo"]


def test_generic_desktop_style_demo_explains_task_failure(
    tmp_path: Path,
) -> None:
    report_path = run_demo(tmp_path / "failure")
    session = read_session_json(report_path.parent / "session.json")

    assert session.goal == "Open Settings and enable dark mode."
    assert session.outcome.value == "failure"
    assert [action.action_type for action in session.actions] == [
        "open_app",
        "click",
    ]
    assert all(action.status is ActionStatus.SUCCESS for action in session.actions)
    assert session.verification is not None
    assert session.verification.passed is False
    assert session.verification.failure_reason == (
        "the agent clicked a setting, but dark mode is still disabled"
    )

    report = report_path.read_text(encoding="utf-8")
    assert "dark mode is still disabled" in report
    screenshots = [
        screenshot
        for action in session.actions
        for screenshot in (
            action.screenshot_before,
            action.screenshot_after,
        )
        if screenshot is not None
    ]
    assert all((report_path.parent / screenshot).is_file() for screenshot in screenshots)
    assert all(
        (report_path.parent / screenshot).read_bytes().startswith(
            b"\x89PNG\r\n\x1a\n"
        )
        for screenshot in screenshots
    )


def test_generic_desktop_style_demo_can_pass(tmp_path: Path) -> None:
    report_path = run_demo(tmp_path / "success", correct=True)
    session = read_session_json(report_path.parent / "session.json")

    assert session.outcome.value == "success"
    assert session.verification is not None
    assert session.verification.passed is True
    assert all(action.status is ActionStatus.SUCCESS for action in session.actions)
