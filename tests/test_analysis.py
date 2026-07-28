from datetime import UTC, datetime
from pathlib import Path

from agent_devtools import (
    ActionRecord,
    ActionSession,
    ActionStatus,
    TrajectoryFinding,
    VerificationResult,
    analyze_session,
)
from agent_devtools.serialization import read_session_json, write_session_json


def _action(
    *,
    action_type: str = "click",
    arguments: dict[str, object] | None = None,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
    changes: list[str] | None = None,
    status: ActionStatus = ActionStatus.SUCCESS,
    verification: VerificationResult | None = None,
) -> ActionRecord:
    observations: dict[str, object] = {}
    if before is not None:
        observations["state_before"] = before
    if after is not None:
        observations["state_after"] = after
    if changes is not None:
        observations["state_changes"] = changes
    return ActionRecord(
        action_type=action_type,
        arguments=arguments or {"selector": "#play"},
        start_time=datetime(2026, 7, 27, tzinfo=UTC),
        duration_ms=10,
        status=status,
        failure_reason=(
            "click failed" if status is ActionStatus.FAILURE else None
        ),
        observations=observations,
        verification=verification,
    )


def test_detects_repeated_successful_actions_without_progress() -> None:
    unchanged = {"url": "https://example.com", "playing": False}
    session = ActionSession(
        actions=[
            _action(before=unchanged, after=unchanged, changes=[])
            for _ in range(3)
        ]
    )

    findings = analyze_session(session)

    assert findings == [
        TrajectoryFinding(
            code="possible_stuck_loop",
            title="Possible stuck loop",
            summary=(
                "Actions 1–3 repeated 'click' with identical arguments, "
                "but the observed state did not change."
            ),
            action_numbers=(1, 2, 3),
            evidence={
                "action_type": "click",
                "arguments": {"selector": "#play"},
                "repeat_count": 3,
            },
            suggestions=(
                "Check whether the target is correct or blocked.",
                "Check whether the agent is deciding from stale state.",
            ),
        )
    ]


def test_does_not_flag_only_two_repeated_actions() -> None:
    unchanged = {"ready": True}
    session = ActionSession(
        actions=[
            _action(before=unchanged, after=unchanged, changes=[])
            for _ in range(2)
        ]
    )

    assert analyze_session(session) == []


def test_does_not_flag_repeated_actions_that_change_state() -> None:
    session = ActionSession(
        actions=[
            _action(
                action_type="scroll",
                arguments={"amount": 500},
                before={"scroll_y": index * 500},
                after={"scroll_y": (index + 1) * 500},
                changes=["scroll_y"],
            )
            for index in range(3)
        ]
    )

    assert analyze_session(session) == []


def test_does_not_guess_without_complete_state_evidence() -> None:
    session = ActionSession(actions=[_action() for _ in range(3)])

    assert analyze_session(session) == []


def test_failure_breaks_repeated_action_run() -> None:
    unchanged = {"ready": True}
    actions = [
        _action(before=unchanged, after=unchanged, changes=[]),
        _action(
            before=unchanged,
            after=unchanged,
            changes=[],
            status=ActionStatus.FAILURE,
        ),
        _action(before=unchanged, after=unchanged, changes=[]),
        _action(before=unchanged, after=unchanged, changes=[]),
    ]

    assert analyze_session(ActionSession(actions=actions)) == []


def test_verification_failure_is_not_duplicated_as_a_finding() -> None:
    unchanged = {"ready": True}
    failed_verification = VerificationResult(
        expected_state="playing",
        observed_state="paused",
        passed=False,
        failure_reason="expected playing, observed paused",
    )
    session = ActionSession(
        actions=[
            _action(
                before=unchanged,
                after=unchanged,
                changes=[],
                verification=failed_verification,
            )
            for _ in range(3)
        ]
    )

    assert analyze_session(session) == []


def test_analyzes_session_loaded_from_existing_json(tmp_path: Path) -> None:
    unchanged = {"ready": True}
    session = ActionSession(
        actions=[
            _action(before=unchanged, after=unchanged, changes=[])
            for _ in range(3)
        ]
    )
    session_path = tmp_path / "session.json"
    write_session_json(session, session_path)

    findings = analyze_session(read_session_json(session_path))

    assert len(findings) == 1
    assert findings[0].code == "possible_stuck_loop"
    assert findings[0].action_numbers == (1, 2, 3)


def test_finds_page_error_during_successful_action() -> None:
    action = _action()
    action.observations["browser_events"] = [
        {
            "event_type": "page_error",
            "message": "player initialization failed",
            "url": "https://example.com/video",
            "count": 1,
        }
    ]

    findings = analyze_session(ActionSession(actions=[action]))

    assert len(findings) == 1
    finding = findings[0]
    assert finding.code == "page_error_during_action"
    assert finding.title == "Page error during action"
    assert finding.action_numbers == (1,)
    assert finding.likely_cause == "player initialization failed"


def test_groups_same_browser_error_across_actions() -> None:
    actions = [_action(), _action()]
    for action in actions:
        action.observations["browser_events"] = [
            {
                "event_type": "console_error",
                "message": "player unavailable",
                "count": 1,
            }
        ]

    findings = analyze_session(ActionSession(actions=actions))

    assert len(findings) == 1
    assert findings[0].code == "console_error_during_action"
    assert findings[0].action_numbers == (1, 2)


def test_reports_network_failure_as_likely_cause() -> None:
    action = _action()
    action.observations["browser_events"] = [
        {
            "event_type": "request_failed",
            "message": "GET fetch request failed: net::ERR_FAILED",
            "method": "GET",
            "resource_type": "fetch",
            "url": "https://example.com/api/search",
            "failure": "net::ERR_FAILED",
            "count": 1,
        }
    ]

    findings = analyze_session(ActionSession(actions=[action]))

    assert len(findings) == 1
    assert findings[0].code == "network_request_failed"
    assert findings[0].title == "Network request failed during action"
    assert findings[0].likely_cause == (
        "GET fetch request failed: net::ERR_FAILED"
    )


def test_prioritizes_api_http_error_over_console_error() -> None:
    action = _action()
    action.observations["browser_events"] = [
        {
            "event_type": "console_error",
            "message": "Failed to load resource",
            "count": 1,
        },
        {
            "event_type": "http_error",
            "message": "POST xhr request returned HTTP 500",
            "method": "POST",
            "resource_type": "xhr",
            "url": "https://example.com/api/save",
            "status": 500,
            "count": 1,
        },
    ]

    findings = analyze_session(ActionSession(actions=[action]))

    assert len(findings) == 1
    assert findings[0].code == "http_error_response"
    assert findings[0].likely_cause == "POST xhr request returned HTTP 500"
