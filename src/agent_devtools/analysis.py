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


def analyze_session(session: ActionSession) -> list[TrajectoryFinding]:
    findings: list[TrajectoryFinding] = []
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
