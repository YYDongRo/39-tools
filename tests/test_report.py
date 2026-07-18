from datetime import UTC, datetime
from pathlib import Path

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.report import write_action_html


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
    assert content.count("Not captured") == 2
