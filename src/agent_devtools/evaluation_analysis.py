from __future__ import annotations

import json
from dataclasses import replace
from statistics import median

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.analysis import TrajectoryFinding, analyze_session
from agent_devtools.evaluation import (
    DivergenceKind,
    EvaluationRun,
    EvaluationRunStatus,
    FailurePattern,
    TrajectoryDivergence,
)
from agent_devtools.session import ActionSession


def analyze_evaluation_runs(
    runs: tuple[EvaluationRun, ...],
    sessions: dict[int, ActionSession],
) -> tuple[
    tuple[EvaluationRun, ...],
    int | None,
    tuple[FailurePattern, ...],
]:
    for run in runs:
        if run.run_number not in sessions:
            raise ValueError(f"missing session for run {run.run_number}")

    representative = _representative_success(runs)
    baseline = sessions[representative] if representative is not None else None
    analyzed_runs = tuple(
        run
        if (
            run.status is EvaluationRunStatus.PASSED
            or run.issue_code is not None
        )
        else replace(
            run,
            divergence=(
                compare_trajectories(baseline, sessions[run.run_number])
                if baseline is not None
                else None
            ),
        )
        for run in runs
    )
    patterns = _group_unsuccessful_runs(analyzed_runs, sessions)
    return analyzed_runs, representative, patterns


def compare_trajectories(
    baseline: ActionSession,
    observed: ActionSession,
) -> TrajectoryDivergence | None:
    candidates: list[tuple[int, int, TrajectoryDivergence]] = []
    direct = _action_divergence(baseline, observed)
    if direct is not None:
        candidates.append((direct.action_number or 10**9, 0, direct))

    finding = _finding_divergence(baseline, observed)
    if finding is not None:
        candidates.append((finding.action_number or 10**9, 1, finding))

    if candidates:
        return min(candidates, key=lambda item: (item[0], item[1]))[2]
    return _final_verification_divergence(baseline, observed)


def _representative_success(runs: tuple[EvaluationRun, ...]) -> int | None:
    successful = [
        run for run in runs if run.status is EvaluationRunStatus.PASSED
    ]
    if not successful:
        return None
    middle = float(median(run.action_count for run in successful))
    return min(
        successful,
        key=lambda run: (abs(run.action_count - middle), run.run_number),
    ).run_number


def _action_divergence(
    baseline: ActionSession,
    observed: ActionSession,
) -> TrajectoryDivergence | None:
    aligned_count = min(len(baseline.actions), len(observed.actions))
    for index in range(aligned_count):
        action_number = index + 1
        expected_action = baseline.actions[index]
        observed_action = observed.actions[index]
        comparisons = (
            (
                DivergenceKind.ACTION_TYPE,
                "action type",
                {"action_type": expected_action.action_type},
                {"action_type": observed_action.action_type},
            ),
            (
                DivergenceKind.ARGUMENTS,
                "action arguments",
                _action_arguments(expected_action),
                _action_arguments(observed_action),
            ),
            (
                DivergenceKind.EXECUTION_STATUS,
                "execution status",
                _execution_result(expected_action),
                _execution_result(observed_action),
            ),
            (
                DivergenceKind.ACTION_VERIFICATION,
                "action verification",
                _action_verification(expected_action),
                _action_verification(observed_action),
            ),
            (
                DivergenceKind.PAGE_URL,
                "page URL",
                _page_urls(expected_action),
                _page_urls(observed_action),
            ),
            (
                DivergenceKind.STATE,
                "compact page state",
                _compact_state(expected_action),
                _compact_state(observed_action),
            ),
        )
        for kind, label, expected_value, observed_value in comparisons:
            if expected_value != observed_value:
                return TrajectoryDivergence(
                    kind=kind,
                    action_number=action_number,
                    summary=(
                        f"First observed divergence at action "
                        f"{action_number}: {label} differed."
                    ),
                    baseline=expected_value,
                    observed=observed_value,
                )

    if len(observed.actions) < len(baseline.actions):
        action_number = len(observed.actions) + 1
        expected_action = baseline.actions[action_number - 1]
        return TrajectoryDivergence(
            kind=DivergenceKind.MISSING_ACTION,
            action_number=action_number,
            summary=(
                f"First observed divergence at action {action_number}: "
                "the unsuccessful trajectory ended early."
            ),
            baseline={
                "action_type": expected_action.action_type,
                "arguments": _action_arguments(expected_action),
            },
            observed={"action": "missing"},
        )
    if len(observed.actions) > len(baseline.actions):
        action_number = len(baseline.actions) + 1
        extra_action = observed.actions[action_number - 1]
        return TrajectoryDivergence(
            kind=DivergenceKind.EXTRA_ACTION,
            action_number=action_number,
            summary=(
                f"First observed divergence at action {action_number}: "
                "the unsuccessful trajectory added an unexpected action."
            ),
            baseline={"action": "missing"},
            observed={
                "action_type": extra_action.action_type,
                "arguments": _action_arguments(extra_action),
            },
        )
    return None


def _finding_divergence(
    baseline: ActionSession,
    observed: ActionSession,
) -> TrajectoryDivergence | None:
    baseline_signatures = {
        _finding_signature(finding) for finding in analyze_session(baseline)
    }
    new_findings = [
        finding
        for finding in analyze_session(observed)
        if _finding_signature(finding) not in baseline_signatures
    ]
    if not new_findings:
        return None
    finding = min(
        new_findings,
        key=lambda value: value.action_numbers[0]
        if value.action_numbers
        else 10**9,
    )
    action_number = finding.action_numbers[0] if finding.action_numbers else None
    browser_finding = finding.code in {
        "network_request_failed",
        "http_error_response",
        "page_error_during_action",
        "console_error_during_action",
    }
    return TrajectoryDivergence(
        kind=(
            DivergenceKind.BROWSER_ERROR
            if browser_finding
            else DivergenceKind.TRAJECTORY_FINDING
        ),
        action_number=action_number,
        summary=(
            f"First observed divergence at action {action_number}: "
            f"{finding.title}."
            if action_number is not None
            else f"Trajectory finding: {finding.title}."
        ),
        baseline={},
        observed={
            "finding_code": finding.code,
            "summary": finding.summary,
            "evidence": finding.evidence,
        },
    )


def _final_verification_divergence(
    baseline: ActionSession,
    observed: ActionSession,
) -> TrajectoryDivergence | None:
    expected = _final_verification(baseline)
    actual = _final_verification(observed)
    if expected == actual:
        return None
    return TrajectoryDivergence(
        kind=DivergenceKind.FINAL_VERIFICATION,
        action_number=None,
        summary=(
            "Actions matched the representative success, but the final "
            "verification result differed."
        ),
        baseline=expected,
        observed=actual,
    )


def _action_arguments(action: ActionRecord) -> dict[str, object]:
    return {
        key: value
        for key, value in action.arguments.items()
        if key != "browser_use_step"
    }


def _execution_result(action: ActionRecord) -> dict[str, object]:
    return {
        "status": action.status.value,
        "failure_category": (
            action.failure_category.value
            if action.failure_category is not None
            else None
        ),
    }


def _action_verification(action: ActionRecord) -> dict[str, object]:
    verification = action.verification
    if verification is None:
        return {"status": "not_configured"}
    return {
        "status": "passed" if verification.passed else "failed",
        "expected_state": verification.expected_state,
        "observed_state": verification.observed_state,
    }


def _page_urls(action: ActionRecord) -> dict[str, object]:
    observations = action.observations
    state_before = observations.get("state_before")
    state_after = observations.get("state_after")
    return {
        "before": observations.get("page_url_before")
        or _state_value(state_before, "url"),
        "after": observations.get("page_url_after")
        or _state_value(state_after, "url"),
    }


def _compact_state(action: ActionRecord) -> dict[str, object]:
    result: dict[str, object] = {}
    for key in ("state_before", "state_after"):
        state = action.observations.get(key)
        if isinstance(state, dict):
            result[key] = {
                state_key: value
                for state_key, value in state.items()
                if state_key not in {"url", "browser_errors"}
            }
    for key in (
        "input_value_after",
        "scroll_before",
        "scroll_after",
        "state_changes",
    ):
        if key in action.observations:
            result[key] = action.observations[key]
    return result


def _state_value(state: object, key: str) -> object:
    return state.get(key) if isinstance(state, dict) else None


def _final_verification(session: ActionSession) -> dict[str, object]:
    verification = session.verification
    if verification is None:
        return {
            "status": "unverified",
            "note": session.verification_note,
        }
    return {
        "status": "passed" if verification.passed else "failed",
        "expected_state": verification.expected_state,
        "observed_state": verification.observed_state,
        "failure_reason": verification.failure_reason,
    }


def _finding_signature(finding: TrajectoryFinding) -> str:
    return _canonical_json(
        {
            "code": finding.code,
            "action_numbers": finding.action_numbers,
            "evidence": finding.evidence,
        }
    )


def _group_unsuccessful_runs(
    runs: tuple[EvaluationRun, ...],
    sessions: dict[int, ActionSession],
) -> tuple[FailurePattern, ...]:
    grouped: dict[
        str,
        tuple[str, list[int], DivergenceKind | None, int | None, dict[str, object]],
    ] = {}
    for run in runs:
        if run.status is EvaluationRunStatus.PASSED:
            continue
        signature, summary, kind, action_number, evidence = _failure_signature(
            run,
            sessions[run.run_number],
        )
        if signature not in grouped:
            grouped[signature] = (summary, [], kind, action_number, evidence)
        grouped[signature][1].append(run.run_number)

    patterns = []
    for index, (_, value) in enumerate(grouped.items(), start=1):
        summary, run_numbers, kind, action_number, evidence = value
        numbers = tuple(run_numbers)
        patterns.append(
            FailurePattern(
                pattern_id=f"pattern-{index:03d}",
                summary=summary,
                run_numbers=numbers,
                representative_run_number=numbers[0],
                divergence_kind=kind,
                action_number=action_number,
                evidence=evidence,
            )
        )
    return tuple(patterns)


def _failure_signature(
    run: EvaluationRun,
    session: ActionSession,
) -> tuple[
    str,
    str,
    DivergenceKind | None,
    int | None,
    dict[str, object],
]:
    if run.issue_code is not None:
        evidence = {
            "issue_code": run.issue_code,
            "run_status": run.status.value,
        }
        return (
            _canonical_json(evidence),
            f"Provider issue: {run.issue_code}.",
            None,
            None,
            evidence,
        )

    if run.divergence is not None:
        divergence = run.divergence
        evidence = {
            "baseline": divergence.baseline,
            "observed": divergence.observed,
            "run_status": run.status.value,
            "error_phase": run.error_phase,
            "error_type": run.error_type,
        }
        signature = _canonical_json(
            {
                "kind": divergence.kind.value,
                "action_number": divergence.action_number,
                **evidence,
            }
        )
        return (
            signature,
            divergence.summary,
            divergence.kind,
            divergence.action_number,
            evidence,
        )

    if run.status is EvaluationRunStatus.ERRORED:
        evidence = {
            "error_phase": run.error_phase,
            "error_type": run.error_type,
        }
        return (
            _canonical_json(evidence),
            f"Run errored during {run.error_phase} ({run.error_type}).",
            None,
            None,
            evidence,
        )

    for action_number, action in enumerate(session.actions, start=1):
        if action.status is ActionStatus.FAILURE:
            evidence = {
                "action_number": action_number,
                "action_type": action.action_type,
                "failure_category": (
                    action.failure_category.value
                    if action.failure_category is not None
                    else None
                ),
            }
            return (
                _canonical_json(evidence),
                f"Action {action_number} failed during {action.action_type}.",
                DivergenceKind.EXECUTION_STATUS,
                action_number,
                evidence,
            )

    findings = analyze_session(session)
    if findings:
        finding = findings[0]
        action_number = (
            finding.action_numbers[0] if finding.action_numbers else None
        )
        evidence = {
            "finding_code": finding.code,
            "action_number": action_number,
        }
        return (
            _canonical_json(evidence),
            finding.summary,
            DivergenceKind.TRAJECTORY_FINDING,
            action_number,
            evidence,
        )

    verification = session.verification
    if verification is not None and not verification.passed:
        evidence = {"failure_reason": verification.failure_reason}
        return (
            _canonical_json(evidence),
            verification.failure_reason or "Final task verification failed.",
            DivergenceKind.FINAL_VERIFICATION,
            None,
            evidence,
        )

    evidence = {"verification_note": session.verification_note}
    return (
        _canonical_json(evidence),
        session.verification_note or "No usable final verification was produced.",
        None,
        None,
        evidence,
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


__all__ = ["analyze_evaluation_runs", "compare_trajectories"]
