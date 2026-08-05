from datetime import UTC, datetime
from pathlib import Path

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.evaluation import DivergenceKind, TrajectoryDivergence
from agent_devtools.failure import FailureCategory
from agent_devtools.integrations.playwright import PlaywrightSessionReplayResult
from agent_devtools.report import (
    ReplayReportSummary,
    ReplayStabilityRunSummary,
    format_session_summary,
    write_action_html,
    write_replay_stability_html,
    write_session_html,
)
from agent_devtools.session import ActionSession
from agent_devtools.verification import VerificationResult


def test_format_successful_session_summary(tmp_path: Path) -> None:
    session = ActionSession(
        goal="Open the requested page",
        actions=[
            ActionRecord(
                action_type="navigate",
                arguments={},
                start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
                duration_ms=32,
                status=ActionStatus.SUCCESS,
            )
        ],
        verification=VerificationResult(
            expected_state="Page open",
            observed_state="Page open",
            passed=True,
        ),
    )
    report_path = tmp_path / "report.html"

    summary = format_session_summary(session, report_path)

    assert summary == "\n".join(
        (
            "Agent DevTools",
            "Task: Open the requested page",
            "Task result: SUCCESS",
            "Actions: 1 (1 succeeded, 0 failed)",
            "Final check: passed",
            f"Report: {report_path.resolve()}",
        )
    )


def test_format_failed_action_summary_is_compact(tmp_path: Path) -> None:
    session = ActionSession(
        goal="Fill the form",
        actions=[
            ActionRecord(
                action_type="fill",
                arguments={"selector": "#readonly"},
                start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
                duration_ms=500,
                status=ActionStatus.FAILURE,
                failure_reason="a very detailed provider or browser error",
                failure_category=FailureCategory.TARGET_NOT_EDITABLE,
            )
        ],
    )

    summary = format_session_summary(session, tmp_path / "report.html")

    assert "Task result: UNVERIFIED" in summary
    assert "Failed at: Action 1 — fill" in summary
    assert "Likely cause: The target was not editable." in summary
    assert "very detailed provider" not in summary


def test_write_successful_action_report(tmp_path: Path) -> None:
    action = ActionRecord(
        action_type="<click>",
        arguments={"selector": "<button>"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.SUCCESS,
        screenshot_before=Path("before.png"),
        screenshot_after=Path("after.png"),
        observations={
            "page_url_before": "https://example.com/search?q=<agent>",
            "page_url_after": "https://example.com/search?q=<agent>",
            "input_value_after": "<Agent debugging>",
        },
    )
    output_path = tmp_path / "trace" / "report.html"

    write_action_html(action, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "&lt;click&gt;" in content
    assert "&lt;button&gt;" in content
    assert (
        'class="status status-neutral">execution succeeded</span>'
        in content
    )
    assert "<dt>Execution status</dt><dd>success</dd>" in content
    assert "<dt>Verification status</dt><dd>not configured</dd>" in content
    assert "Observations" in content
    assert (
        "<dt>Input value after</dt><dd>&lt;Agent debugging&gt;</dd>"
        in content
    )
    assert "&quot;input_value_after&quot;" not in content
    assert "<dt>Page URL</dt>" in content
    assert "https://example.com/search?q=&lt;agent&gt;" in content
    assert "Page URL before" not in content
    assert "Page URL after" not in content
    assert "page_url_before" not in content
    assert "page_url_after" not in content
    assert 'src="before.png"' in content
    assert 'src="after.png"' in content


def test_report_shows_friendly_arguments_and_collapses_raw_values(
    tmp_path: Path,
) -> None:
    action = ActionRecord(
        action_type="navigate",
        arguments={
            "url": "https://example.com",
            "new_tab": False,
            "browser_use_step": 1,
        },
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.SUCCESS,
    )
    action_output = tmp_path / "action.html"
    session_output = tmp_path / "session.html"

    write_action_html(action, action_output)
    write_session_html(ActionSession(actions=[action]), session_output)

    for output_path in (action_output, session_output):
        content = output_path.read_text(encoding="utf-8")
        assert "Target URL" in content
        assert "https://example.com" in content
        assert "New tab" in content
        assert '<summary>Technical details</summary>' in content
        assert 'class="technical-details"' in content
        assert "browser_use_step" in content


def test_report_displays_changed_page_urls_compactly(tmp_path: Path) -> None:
    action = ActionRecord(
        action_type="navigate",
        arguments={"url": "https://example.com/video"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.SUCCESS,
        observations={
            "page_url_before": "about:blank",
            "page_url_after": "https://example.com/video",
        },
    )
    action_output = tmp_path / "action.html"
    session_output = tmp_path / "session.html"

    write_action_html(action, action_output)
    write_session_html(ActionSession(actions=[action]), session_output)

    for output_path in (action_output, session_output):
        content = output_path.read_text(encoding="utf-8")
        assert "<dt>Page URL before</dt><dd>about:blank</dd>" in content
        assert (
            "<dt>Page URL after</dt>"
            "<dd>https://example.com/video</dd>"
        ) in content
        assert "Observations" not in content
        assert "page_url_before" not in content
        assert "page_url_after" not in content


def test_report_displays_structured_state_compactly(tmp_path: Path) -> None:
    action = ActionRecord(
        action_type="click",
        arguments={"selector": "#search"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.SUCCESS,
        observations={
            "state_before": {
                "url": "https://example.com/&lt;before&gt;",
                "scroll": {"x": 0, "y": 0},
            },
            "state_after": {
                "url": "https://example.com/<after>",
                "scroll": {"x": 0, "y": 100},
            },
            "state_changes": ["scroll.y", "url"],
        },
    )
    action_output = tmp_path / "action.html"
    session_output = tmp_path / "session.html"

    write_action_html(action, action_output)
    write_session_html(ActionSession(actions=[action]), session_output)

    for output_path in (action_output, session_output):
        content = output_path.read_text(encoding="utf-8")
        assert "Structured state" in content
        assert "Detected changes" in content
        assert "<li>scroll.y</li>" in content
        assert "<li>url</li>" in content
        assert "<summary>State before</summary>" in content
        assert "<summary>State after</summary>" in content
        assert "https://example.com/&lt;after&gt;" in content
        assert "<dt>State Before</dt>" not in content


def test_report_displays_observer_failure_without_raw_message(
    tmp_path: Path,
) -> None:
    action = ActionRecord(
        action_type="click",
        arguments={},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.SUCCESS,
        observations={
            "state_before_error_type": "RuntimeError",
            "state_after": {"ready": True},
        },
    )
    output_path = tmp_path / "report.html"

    write_action_html(action, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "Before observation unavailable (RuntimeError)." in content
    assert "State changes unavailable." in content
    assert "<summary>State after</summary>" in content


def test_write_failed_action_report_without_screenshots(tmp_path: Path) -> None:
    action = ActionRecord(
        action_type="click",
        arguments={},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=250,
        status=ActionStatus.FAILURE,
        failure_reason=(
            "Element <button> was not found\n"
            "Call log:\n"
            "- waiting for locator"
        ),
        failure_evidence={"selector": "<button>", "selector_count": 0},
        observations={"input_value_after": ""},
    )
    output_path = tmp_path / "report.html"

    write_action_html(action, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert 'class="status status-failure"' in content
    assert "Element &lt;button&gt; was not found" in content
    assert "<strong>Category:</strong> unknown" in content
    assert "Diagnostic evidence" in content
    assert "&lt;button&gt;" in content
    assert "<dt>Matches</dt><dd>0</dd>" in content
    assert '<details class="raw-error">' in content
    assert "<summary>Raw error details</summary>" in content
    assert "Call log:" in content
    assert "<dt>Input value after</dt><dd>\"\"</dd>" in content
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
    assert '<strong class="result-title">Completed with failures</strong>' in content
    assert '<span>Actions</span><strong>3</strong>' in content
    assert '<span>Executed</span><strong>1 succeeded</strong>' in content
    assert '<span>Action failures</span><strong>2</strong>' in content
    assert '<span>Action checks</span><strong>1 of 3 run</strong>' in content
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
    assert "<dt>Visible</dt><dd>true</dd>" in content
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
    assert '<span>Actions</span><strong>1</strong>' in content
    assert '<span>Executed</span><strong>1 succeeded</strong>' in content
    assert '<span>Action failures</span><strong>0</strong>' in content
    assert '<span>Action checks</span><strong>1 run</strong>' in content
    assert "Failure categories" not in content
    assert "Potential issues" not in content


def test_session_report_highlights_possible_stuck_loop_cleanly(
    tmp_path: Path,
) -> None:
    unchanged = {"url": "https://example.com", "playing": False}
    session = ActionSession(
        actions=[
            ActionRecord(
                action_type="click",
                arguments={"selector": "<#play>"},
                start_time=datetime(2026, 7, 18, 7, index, tzinfo=UTC),
                duration_ms=32,
                status=ActionStatus.SUCCESS,
                observations={
                    "state_before": unchanged,
                    "state_after": unchanged,
                    "state_changes": [],
                },
            )
            for index in range(3)
        ]
    )
    output_path = tmp_path / "session.html"

    write_session_html(session, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert '<h2 id="findings-title">Potential issues</h2>' in content
    assert '<span class="findings-count">1 warning</span>' in content
    assert "Possible stuck loop" in content
    assert (
        "Actions 1–3 repeated &#x27;click&#x27; with identical arguments, "
        "but the observed state did not change."
    ) in content
    assert '<a href="#action-1">Action 1</a>' in content
    assert '<a href="#action-3">Action 3</a>' in content
    assert '<article class="timeline-item" id="action-1">' in content
    assert '<details class="finding-details">' in content
    assert "Evidence and what to inspect" in content
    assert "Check whether the target is correct or blocked." in content
    assert "&lt;#play&gt;" in content
    assert "They do not change the recorded task outcome." in content


def test_session_report_shows_likely_browser_cause_without_clutter(
    tmp_path: Path,
) -> None:
    action = ActionRecord(
        action_type="click",
        arguments={"selector": "#play"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.SUCCESS,
        observations={
            "browser_events": [
                {
                    "event_type": "page_error",
                    "message": "player <initialization> failed",
                    "url": "https://example.com/video",
                    "count": 1,
                }
            ]
        },
    )
    output_path = tmp_path / "session.html"

    write_session_html(ActionSession(actions=[action]), output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "Page error during action" in content
    assert "<strong>Likely cause:</strong> player &lt;initialization&gt; failed" in content
    assert "Browser evidence (1 event)" in content
    assert '<section class="browser-evidence">' in content
    assert "browser_events" not in content


def test_session_report_shows_http_error_as_likely_cause(
    tmp_path: Path,
) -> None:
    action = ActionRecord(
        action_type="click",
        arguments={"selector": "#search"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.SUCCESS,
        observations={
            "browser_events": [
                {
                    "event_type": "http_error",
                    "message": "POST xhr request returned HTTP 500",
                    "method": "POST",
                    "resource_type": "xhr",
                    "url": "https://example.com/api/search",
                    "status": 500,
                    "count": 1,
                }
            ]
        },
    )
    output_path = tmp_path / "session.html"

    write_session_html(ActionSession(actions=[action]), output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "HTTP error response during action" in content
    assert (
        "<strong>Likely cause:</strong> "
        "POST xhr request returned HTTP 500"
    ) in content
    assert "Browser evidence (1 event)" in content


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
    assert '<strong class="result-title">Execution completed</strong>' in content
    assert "All recorded actions executed successfully." in content
    assert '<span>Action checks</span><strong>Not configured</strong>' in content
    assert 'class="status status-neutral">execution succeeded</span>' in content
    assert "unverified action" not in content


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
    assert '<strong class="result-title">Successful</strong>' in content
    assert "<strong>User request:</strong> Play the &lt;video&gt;" in content
    assert "Final checks" in content
    assert 'class="check-total check-total-passed">passed</span>' in content
    assert "&lt;player-status&gt;" in content


def test_session_report_collapses_verbose_ai_success_explanation(
    tmp_path: Path,
) -> None:
    explanation = (
        "The agent completed every requested action and confirmed the final "
        "page state with additional evidence."
    )
    session = ActionSession(
        goal="Open the page",
        actions=[],
        verification=VerificationResult(
            expected_state="Page open",
            observed_state=explanation,
            passed=True,
            evidence={"assessment_type": "ai_final_state"},
        ),
    )
    output_path = tmp_path / "session.html"

    write_session_html(session, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "Final task check passed." in content
    assert '<details class="assessment-summary">' in content
    assert "<summary>Judge explanation</summary>" in content
    assert explanation in content


def test_session_report_displays_automatic_verification_metadata(
    tmp_path: Path,
) -> None:
    session = ActionSession(
        goal="Open & inspect the page",
        inferred_goal="Reach the expected page",
        verification_source="openai:gpt-test",
        verification_note="No reliable selector was available.",
    )
    output_path = tmp_path / "session.html"

    write_session_html(session, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "<strong>User request:</strong> Open &amp; inspect the page" in content
    assert "<strong>Inferred goal:</strong> Reach the expected page" in content
    assert "Verification context" in content
    assert "<strong>Source:</strong> openai:gpt-test" in content
    assert "<strong>Verification note:</strong>" in content
    assert "No reliable selector was available." in content


def test_session_report_displays_reproduced_replay_verdict(
    tmp_path: Path,
) -> None:
    source_action = ActionRecord(
        action_type="click",
        arguments={"selector": "#target"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.SUCCESS,
    )
    replayed_action = ActionRecord(
        action_type="click",
        arguments={"selector": "#target"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.SUCCESS,
    )
    output_path = tmp_path / "replay.html"

    write_session_html(
        ActionSession(actions=[replayed_action]),
        output_path,
        replay_summary=ReplayReportSummary(
            target_action_number=2,
            source_action=source_action,
            replayed_action=replayed_action,
            reproduced=True,
            target_action_selection_note=(
                "Automatically selected the first failed action."
            ),
        ),
    )

    content = output_path.read_text(encoding="utf-8")
    assert '<strong class="replay-verdict">Reproduced</strong>' in content
    assert "The replay matched the original target outcome." in content
    assert "Original target" in content
    assert "Replay target" in content
    assert "1 preceding action rebuilt." in content
    assert "Automatically selected the first failed action." in content


def test_session_report_displays_unreproduced_replay_verdict(
    tmp_path: Path,
) -> None:
    source_action = ActionRecord(
        action_type="fill",
        arguments={"selector": "#missing", "text": "Agent debugging"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.FAILURE,
        failure_reason="The target was not found.",
        failure_category=FailureCategory.TARGET_NOT_FOUND,
    )
    replayed_action = ActionRecord(
        action_type="fill",
        arguments={"selector": "#missing", "text": "Agent debugging"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.SUCCESS,
    )
    output_path = tmp_path / "replay.html"

    write_session_html(
        ActionSession(actions=[replayed_action]),
        output_path,
        replay_summary=ReplayReportSummary(
            target_action_number=2,
            source_action=source_action,
            replayed_action=replayed_action,
            reproduced=False,
        ),
    )

    content = output_path.read_text(encoding="utf-8")
    assert '<strong class="replay-verdict">Not reproduced</strong>' in content
    assert "The replay did not match the original target outcome." in content
    assert "failure · target_not_found" in content
    assert "1 preceding action rebuilt." in content


def test_session_report_collapses_replay_first_difference(
    tmp_path: Path,
) -> None:
    source_action = ActionRecord(
        action_type="fill",
        arguments={"selector": "#search", "text": "headphones"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.FAILURE,
        failure_reason="The target was not found.",
        failure_category=FailureCategory.TARGET_NOT_FOUND,
    )
    replayed_action = ActionRecord(
        action_type="fill",
        arguments={"selector": "#search", "text": "headphones"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.SUCCESS,
    )
    divergence = TrajectoryDivergence(
        kind=DivergenceKind.EXECUTION_STATUS,
        action_number=2,
        summary="First observed divergence at action 2: execution status differed.",
        baseline={"status": "failure"},
        observed={"status": "success"},
    )
    output_path = tmp_path / "replay.html"

    write_session_html(
        ActionSession(actions=[replayed_action]),
        output_path,
        replay_summary=ReplayReportSummary(
            target_action_number=2,
            source_action=source_action,
            replayed_action=replayed_action,
            reproduced=False,
            first_divergence=divergence,
        ),
    )

    content = output_path.read_text(encoding="utf-8")
    assert "First difference · Action 2 · execution status differed." in content
    assert "First observed divergence at action 2" in content
    assert 'class="replay-divergence"' in content
    assert "&quot;status&quot;: &quot;failure&quot;" in content
    assert "&quot;status&quot;: &quot;success&quot;" in content


def test_playwright_replay_result_exposes_first_difference() -> None:
    source_action = ActionRecord(
        action_type="click",
        arguments={"selector": "#target"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.FAILURE,
        failure_reason="The target was not found.",
        failure_category=FailureCategory.TARGET_NOT_FOUND,
    )
    replayed_action = ActionRecord(
        action_type="click",
        arguments={"selector": "#target"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.SUCCESS,
    )
    result = PlaywrightSessionReplayResult(
        source_session=ActionSession(actions=[source_action]),
        replayed_session=ActionSession(actions=[replayed_action]),
        target_action_number=1,
        target_result=None,
        context_failure_action_number=None,
        report_path=Path("report.html"),
    )

    assert result.first_divergence is not None
    assert result.first_divergence.kind is DivergenceKind.EXECUTION_STATUS
    assert result.first_divergence.action_number == 1


def test_replay_stability_report_summarizes_mixed_results(
    tmp_path: Path,
) -> None:
    source_action = ActionRecord(
        action_type="fill",
        arguments={"selector": "#missing", "text": "Agent debugging"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.FAILURE,
        failure_reason="The target was not found.",
        failure_category=FailureCategory.TARGET_NOT_FOUND,
    )
    matching_action = ActionRecord(
        action_type="fill",
        arguments={"selector": "#missing", "text": "Agent debugging"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.FAILURE,
        failure_reason="The target was not found.",
        failure_category=FailureCategory.TARGET_NOT_FOUND,
    )
    successful_action = ActionRecord(
        action_type="fill",
        arguments={"selector": "#missing", "text": "Agent debugging"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.SUCCESS,
    )
    divergence = TrajectoryDivergence(
        kind=DivergenceKind.EXECUTION_STATUS,
        action_number=2,
        summary="First observed divergence at action 2: execution status differed.",
        baseline={"status": "failure"},
        observed={"status": "success"},
    )
    output_path = tmp_path / "stability.html"

    write_replay_stability_html(
        output_path,
        target_action_number=2,
        source_action=source_action,
        runs=(
            ReplayStabilityRunSummary(
                1,
                ReplayReportSummary(2, source_action, matching_action, True),
                Path("runs/001/report.html"),
            ),
            ReplayStabilityRunSummary(
                2,
                ReplayReportSummary(
                    2,
                    source_action,
                    successful_action,
                    False,
                    first_divergence=divergence,
                ),
                Path("runs/002/report.html"),
            ),
            ReplayStabilityRunSummary(
                3,
                ReplayReportSummary(2, source_action, matching_action, True),
                Path("runs/003/report.html"),
            ),
        ),
    )

    content = output_path.read_text(encoding="utf-8")
    assert "Intermittent replay result" in content
    assert "Total replays" in content and "<strong>3</strong>" in content
    assert "Reproduced" in content and "<strong>2</strong>" in content
    assert "Not reproduced" in content and "<strong>1</strong>" in content
    assert 'href="runs/001/report.html"' in content
    assert 'href="runs/003/report.html"' in content
    assert "failure · target_not_found" in content
    assert "Action 2 · execution status differed." in content
    assert "First difference" in content


def test_replay_stability_report_displays_target_selection_note(
    tmp_path: Path,
) -> None:
    source_action = ActionRecord(
        action_type="fill",
        arguments={"selector": "#missing", "text": "Agent debugging"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=32,
        status=ActionStatus.FAILURE,
        failure_reason="The target was not found.",
        failure_category=FailureCategory.TARGET_NOT_FOUND,
    )
    output_path = tmp_path / "stability.html"

    write_replay_stability_html(
        output_path,
        target_action_number=1,
        source_action=source_action,
        runs=(
            ReplayStabilityRunSummary(
                1,
                ReplayReportSummary(1, source_action, source_action, True),
                Path("runs/001/report.html"),
            ),
        ),
        target_action_selection_note=(
            "Automatically selected the first failed action."
        ),
    )

    content = output_path.read_text(encoding="utf-8")
    assert "Selection" in content
    assert "Automatically selected the first failed action." in content


def test_session_report_displays_agent_run_failure(
    tmp_path: Path,
) -> None:
    session = ActionSession(
        goal="Open the product page",
        verification_source="agent-run",
        verification_note="Agent run failed (RuntimeError).",
    )
    output_path = tmp_path / "session.html"

    write_session_html(session, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert '<strong class="result-title">Agent run failed</strong>' in content
    assert "<strong>Agent run failure:</strong>" in content
    assert "Agent run failed (RuntimeError)." in content


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
    assert '<strong class="result-title">Failed</strong>' in content
    assert "Final checks" in content
    assert 'class="check-total check-total-failed">failed</span>' in content
    assert "expected &#x27;Playing&#x27;, observed &#x27;Paused&#x27;" in content


def test_write_empty_session_report(tmp_path: Path) -> None:
    output_path = tmp_path / "session.html"

    write_session_html(ActionSession(), output_path)

    content = output_path.read_text(encoding="utf-8")
    assert '<strong class="result-title">No actions</strong>' in content
    assert '<span>Actions</span><strong>0</strong>' in content
    assert '<span>Action checks</span><strong>Not configured</strong>' in content
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
    assert '<strong class="result-title">Completed with failures</strong>' in session_content
    assert '<span>Action failures</span><strong>1</strong>' in session_content
    assert "<span>verification_mismatch</span><strong>1</strong>" in session_content
