from datetime import UTC, datetime
from pathlib import Path

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.report import write_action_html, write_session_html
from agent_devtools.session import ActionSession
from agent_devtools.verification import VerificationResult


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
    assert 'class="status status-unverified"' in content
    assert "<dt>Execution status</dt><dd>success</dd>" in content
    assert "<dt>Verification status</dt><dd>not run</dd>" in content
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
        failure_evidence={"selector": "<button>", "selector_count": 0},
    )
    output_path = tmp_path / "report.html"

    write_action_html(action, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert 'class="status status-failure"' in content
    assert "Element &lt;button&gt; was not found" in content
    assert "<strong>Category:</strong> unknown" in content
    assert "Diagnostic evidence" in content
    assert "&lt;button&gt;" in content
    assert "&quot;selector_count&quot;: 0" in content
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
                verification=VerificationResult(
                    expected_state="Clicked",
                    observed_state="Clicked",
                    passed=True,
                ),
            ),
            ActionRecord(
                action_type="<click>",
                arguments={"selector": "#missing-agent-action"},
                start_time=datetime(2026, 7, 18, 7, 1, tzinfo=UTC),
                duration_ms=508,
                status=ActionStatus.FAILURE,
                failure_reason="Element <button> was not found",
            ),
            ActionRecord(
                action_type="click",
                arguments={"selector": "#slow-action"},
                start_time=datetime(2026, 7, 18, 7, 2, tzinfo=UTC),
                duration_ms=1000,
                status=ActionStatus.FAILURE,
                failure_reason="TimeoutError: target did not appear",
                failure_category=FailureCategory.TIMEOUT,
                failure_evidence={
                    "selector": "#slow-action",
                    "selector_count": 1,
                    "target_visible": True,
                    "target_enabled": True,
                },
            ),
        ]
    )
    output_path = tmp_path / "session.html"

    write_session_html(session, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert (
        "3 actions · 1 verified success · 2 failures · 0 unverified actions"
        in content
    )
    assert "Action 1" in content
    assert "Action 2" in content
    assert "Action 3" in content
    assert 'class="status status-success"' in content
    assert 'class="status status-failure"' in content
    assert "&lt;click&gt;" in content
    assert "Element &lt;button&gt; was not found" in content
    assert "<strong>Category:</strong> unknown" in content
    assert "Failure categories" in content
    assert "<span>timeout</span><strong>1</strong>" in content
    assert "<span>unknown</span><strong>1</strong>" in content
    assert "Diagnostic evidence" in content
    assert "&quot;target_visible&quot;: true" in content
    assert 'src="action-1/before.png"' in content


def test_successful_session_omits_failure_summary(tmp_path: Path) -> None:
    session = ActionSession(
        actions=[
            ActionRecord(
                action_type="click",
                arguments={},
                start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
                duration_ms=32,
                status=ActionStatus.SUCCESS,
                verification=VerificationResult(
                    expected_state="Ready",
                    observed_state="Ready",
                    passed=True,
                ),
            )
        ]
    )
    output_path = tmp_path / "session.html"

    write_session_html(session, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert (
        "1 action · 1 verified success · 0 failures · 0 unverified actions"
        in content
    )
    assert "Failure categories" not in content


def test_session_report_marks_missing_verification_as_unverified(
    tmp_path: Path,
) -> None:
    session = ActionSession(
        actions=[
            ActionRecord(
                action_type="click",
                arguments={},
                start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
                duration_ms=32,
                status=ActionStatus.SUCCESS,
            )
        ]
    )
    output_path = tmp_path / "session.html"

    write_session_html(session, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert (
        "1 action · 0 verified successes · 0 failures · 1 unverified action"
        in content
    )
    assert "contains unverified actions" in content
    assert 'class="status status-unverified"' in content


def test_session_report_displays_successful_task_verification(
    tmp_path: Path,
) -> None:
    session = ActionSession(
        actions=[
            ActionRecord(
                action_type="click",
                arguments={"selector": "#play"},
                start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
                duration_ms=32,
                status=ActionStatus.SUCCESS,
            )
        ],
        goal="Play the <video>",
        verification=VerificationResult(
            expected_state="Playing",
            observed_state="Playing",
            passed=True,
            evidence={"selector": "<player-status>"},
        ),
    )
    output_path = tmp_path / "session.html"

    write_session_html(session, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert 'class="status status-success">task successful</span>' in content
    assert "<strong>Goal:</strong> Play the &lt;video&gt;" in content
    assert "Task verification" in content
    assert "<dt>Status</dt><dd>passed</dd>" in content
    assert "&lt;player-status&gt;" in content


def test_session_report_displays_failed_task_verification(tmp_path: Path) -> None:
    session = ActionSession(
        goal="Play the video",
        verification=VerificationResult(
            expected_state="Playing",
            observed_state="Paused",
            passed=False,
            failure_reason="expected 'Playing', observed 'Paused'",
        ),
    )
    output_path = tmp_path / "session.html"

    write_session_html(session, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert 'class="status status-failure">task failed</span>' in content
    assert "Task verification" in content
    assert "<dt>Status</dt><dd>failed</dd>" in content
    assert "expected &#x27;Playing&#x27;, observed &#x27;Paused&#x27;" in content


def test_write_empty_session_report(tmp_path: Path) -> None:
    output_path = tmp_path / "session.html"

    write_session_html(ActionSession(), output_path)

    content = output_path.read_text(encoding="utf-8")
    assert (
        "0 actions · 0 verified successes · 0 failures · 0 unverified actions"
        in content
    )
    assert 'class="status status-empty"' in content
    assert "No actions recorded." in content
    assert "Failure categories" not in content


def test_report_displays_verification_failure_as_final_failure(
    tmp_path: Path,
) -> None:
    action = ActionRecord(
        action_type="click",
        arguments={"selector": "#save"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.SUCCESS,
        verification=VerificationResult(
            expected_state="<Saved>",
            observed_state="<Saving>",
            passed=False,
            evidence={"selector": "<status>"},
            failure_reason="expected <Saved>, observed <Saving>",
        ),
    )
    action_output = tmp_path / "action.html"
    session_output = tmp_path / "session.html"

    write_action_html(action, action_output)
    write_session_html(ActionSession(actions=[action]), session_output)

    action_content = action_output.read_text(encoding="utf-8")
    assert 'class="status status-failure"' in action_content
    assert "<dt>Execution status</dt><dd>success</dd>" in action_content
    assert "<dt>Verification status</dt><dd>failed</dd>" in action_content
    assert "&lt;Saved&gt;" in action_content
    assert "&lt;Saving&gt;" in action_content
    assert "expected &lt;Saved&gt;, observed &lt;Saving&gt;" in action_content
    assert "Verification evidence" in action_content
    assert "&lt;status&gt;" in action_content

    session_content = session_output.read_text(encoding="utf-8")
    assert (
        "1 action · 0 verified successes · 1 failure · 0 unverified actions"
        in session_content
    )
    assert "contains failures" in session_content
    assert "<span>verification_mismatch</span><strong>1</strong>" in session_content
