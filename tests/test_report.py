from datetime import UTC, datetime
from pathlib import Path

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.report import write_action_html, write_session_html
from agent_devtools.session import ActionSession


def test_write_successful_action_report(tmp_path: Path) -> None:
    action = ActionRecord(
        action_type="<click>",
        arguments={"selector": "<button>"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.SUCCESS,
        screenshot_before=Path("before.png"),
        screenshot_after=Path("after.png"),
    )
    output_path = tmp_path / "trace" / "report.html"

    write_action_html(action, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "&lt;click&gt;" in content
    assert "&lt;button&gt;" in content
    assert 'class="status status-success"' in content
    assert 'src="before.png"' in content
    assert 'src="after.png"' in content


def test_write_failed_action_report_without_screenshots(tmp_path: Path) -> None:
    action = ActionRecord(
        action_type="click",
        arguments={},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=250,
        status=ActionStatus.FAILURE,
        failure_reason="Element <button> was not found",
    )
    output_path = tmp_path / "report.html"

    write_action_html(action, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert 'class="status status-failure"' in content
    assert "Element &lt;button&gt; was not found" in content
    assert "<strong>Category:</strong> unknown" in content
    assert content.count("Not captured") == 2


def test_write_mixed_session_report(tmp_path: Path) -> None:
    session = ActionSession(
        actions=[
            ActionRecord(
                action_type="click",
                arguments={"selector": "#agent-action"},
                start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
                duration_ms=32,
                status=ActionStatus.SUCCESS,
                screenshot_before=Path("action-1/before.png"),
                screenshot_after=Path("action-1/after.png"),
            ),
            ActionRecord(
                action_type="<click>",
                arguments={"selector": "#missing-agent-action"},
                start_time=datetime(2026, 7, 18, 7, 1, tzinfo=UTC),
                duration_ms=508,
                status=ActionStatus.FAILURE,
                failure_reason="Element <button> was not found",
            ),
        ]
    )
    output_path = tmp_path / "session.html"

    write_session_html(session, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "2 actions · 1 failure" in content
    assert "Action 1" in content
    assert "Action 2" in content
    assert 'class="status status-success"' in content
    assert 'class="status status-failure"' in content
    assert "&lt;click&gt;" in content
    assert "Element &lt;button&gt; was not found" in content
    assert "<strong>Category:</strong> unknown" in content
    assert 'src="action-1/before.png"' in content


def test_write_empty_session_report(tmp_path: Path) -> None:
    output_path = tmp_path / "session.html"

    write_session_html(ActionSession(), output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "0 actions · 0 failures" in content
    assert 'class="status status-empty"' in content
    assert "No actions recorded." in content
