from dataclasses import dataclass, field

from agent_devtools.action import ActionOutcome, ActionRecord, ActionStatus
from agent_devtools.session import ActionSession


@dataclass(frozen=True)
class TrajectoryFinding:
    code: str
    title: str
    summary: str
    action_numbers: tuple[int, ...]
    evidence: dict[str, object] = field(default_factory=dict)
    suggestions: tuple[str, ...] = ()
    likely_cause: str | None = None


def analyze_session(session: ActionSession) -> list[TrajectoryFinding]:
    findings = _browser_error_findings(session)
    run_start = 0

    while run_start < len(session.actions):
        first = session.actions[run_start]
        if not _is_successful_no_progress_action(first):
            run_start += 1
            continue

        run_end = run_start + 1
        while run_end < len(session.actions):
            candidate = session.actions[run_end]
            if not _is_successful_no_progress_action(candidate):
                break
            if not _same_action(first, candidate):
                break
            run_end += 1

        repeat_count = run_end - run_start
        if repeat_count >= 3:
            action_numbers = tuple(range(run_start + 1, run_end + 1))
            findings.append(
                TrajectoryFinding(
                    code="possible_stuck_loop",
                    title="Possible stuck loop",
                    summary=(
                        f"Actions {action_numbers[0]}–{action_numbers[-1]} "
                        f"repeated {first.action_type!r} with identical "
                        "arguments, but the observed state did not change."
                    ),
                    action_numbers=action_numbers,
                    evidence={
                        "action_type": first.action_type,
                        "arguments": dict(first.arguments),
                        "repeat_count": repeat_count,
                    },
                    suggestions=(
                        "Check whether the target is correct or blocked.",
                        "Check whether the agent is deciding from stale state.",
                    ),
                )
            )

        run_start = run_end

    return findings


def _browser_error_findings(
    session: ActionSession,
) -> list[TrajectoryFinding]:
    grouped: dict[
        tuple[str, str, str],
        tuple[dict[str, object], list[int]],
    ] = {}
    for action_number, action in enumerate(session.actions, start=1):
        event = _primary_browser_error(action)
        if event is None:
            continue
        event_type = event["event_type"]
        message = event["message"]
        url = event.get("url", "")
        if not isinstance(url, str):
            url = ""
        key = (event_type, message, url)
        if key not in grouped:
            grouped[key] = (event, [])
        grouped[key][1].append(action_number)

    findings: list[TrajectoryFinding] = []
    for (event_type, message, _), (event, action_numbers) in grouped.items():
        numbers = tuple(action_numbers)
        action_label = (
            f"Action {numbers[0]}"
            if len(numbers) == 1
            else "Actions " + ", ".join(str(number) for number in numbers)
        )
        code, title, event_summary, suggestions = _browser_finding_details(
            event_type
        )
        findings.append(
            TrajectoryFinding(
                code=code,
                title=title,
                summary=(
                    f"{action_label} reported {event_summary}."
                ),
                action_numbers=numbers,
                evidence=dict(event),
                suggestions=suggestions,
                likely_cause=message,
            )
        )
    return findings


def _primary_browser_error(
    action: ActionRecord,
) -> dict[str, str | int] | None:
    events = action.observations.get("browser_events")
    if not isinstance(events, list):
        return None
    valid_events = [
        event
        for event in events
        if isinstance(event, dict)
        and event.get("event_type")
        in {"page_error", "console_error", "request_failed", "http_error"}
        and isinstance(event.get("message"), str)
        and bool(event["message"])
    ]
    if not valid_events:
        return None
    return min(  # type: ignore[return-value]
        valid_events,
        key=_browser_event_priority,
    )


def _browser_event_priority(event: dict[str, object]) -> int:
    event_type = event.get("event_type")
    resource_type = event.get("resource_type")
    important_resource = resource_type in {
        "document",
        "xhr",
        "fetch",
        "script",
        "media",
    }
    if event_type == "request_failed":
        return 0 if important_resource else 4
    if event_type == "http_error":
        return 1 if important_resource else 5
    if event_type == "page_error":
        return 2
    return 3


def _browser_finding_details(
    event_type: str,
) -> tuple[str, str, str, tuple[str, ...]]:
    if event_type == "request_failed":
        return (
            "network_request_failed",
            "Network request failed during action",
            "a network request failure",
            (
                "Check connectivity, DNS, request blocking, and timeouts.",
                "Check whether the failed resource was required for the "
                "UI update.",
            ),
        )
    if event_type == "http_error":
        return (
            "http_error_response",
            "HTTP error response during action",
            "an HTTP error response",
            (
                "Inspect the failing endpoint and server-side logs.",
                "Check whether authentication or rate limiting caused the "
                "response.",
            ),
        )
    if event_type == "page_error":
        return (
            "page_error_during_action",
            "Page error during action",
            "a JavaScript error",
            (
                "Inspect the application code associated with this action.",
                "Check whether the error prevented the expected UI update.",
            ),
        )
    return (
        "console_error_during_action",
        "Console error during action",
        "a console error",
        (
            "Inspect the application code associated with this action.",
            "Check whether the error prevented the expected UI update.",
        ),
    )


def _is_successful_no_progress_action(action: ActionRecord) -> bool:
    if action.status is not ActionStatus.SUCCESS:
        return False
    if action.outcome is ActionOutcome.FAILURE:
        return False

    state_before = action.observations.get("state_before")
    state_after = action.observations.get("state_after")
    if not isinstance(state_before, dict) or not isinstance(state_after, dict):
        return False
    if state_before != state_after:
        return False

    changes = action.observations.get("state_changes")
    return changes is None or changes == []


def _same_action(first: ActionRecord, second: ActionRecord) -> bool:
    return (
        first.action_type == second.action_type
        and first.arguments == second.arguments
    )
