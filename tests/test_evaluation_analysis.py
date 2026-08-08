from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.evaluation import (
    DivergenceKind,
    EvaluationRun,
    EvaluationRunStatus,
)
from agent_devtools.evaluation_analysis import (
    analyze_evaluation_runs,
    compare_trajectories,
)
from agent_devtools.session import ActionSession
from agent_devtools.verification import VerificationResult


START = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def action(
    action_type: str = "click",
    arguments: dict[str, object] | None = None,
    *,
    status: ActionStatus = ActionStatus.SUCCESS,
    before_url: str = "https://shop.example.test/search",
    after_url: str = "https://shop.example.test/product",
    state_after: dict[str, object] | None = None,
    browser_events: list[dict[str, object]] | None = None,
    verification: VerificationResult | None = None,
) -> ActionRecord:
    observations: dict[str, object] = {
        "state_before": {"url": before_url, "title": "Search"},
        "state_after": state_after
        or {"url": after_url, "title": "Product"},
    }
    if browser_events is not None:
        observations["browser_events"] = browser_events
    return ActionRecord(
        action_type=action_type,
        arguments=arguments or {"selector": "#product", "browser_use_step": 4},
        start_time=START,
        duration_ms=20,
        status=status,
        failure_reason="click failed" if status is ActionStatus.FAILURE else None,
        observations=observations,
        verification=verification,
    )


def verified_session(
    actions: list[ActionRecord],
    *,
    passed: bool = True,
    note: str | None = None,
) -> ActionSession:
    verification = VerificationResult(
        expected_state="Correct product is open",
        observed_state=(
            "Correct product is open" if passed else "Wrong product is open"
        ),
        passed=passed,
        failure_reason=None if passed else "Wrong product was selected",
    )
    return ActionSession(
        actions=actions,
        goal="Open the correct product",
        verification=verification,
        verification_note=note,
    )


def run(
    run_number: int,
    status: EvaluationRunStatus,
    action_count: int,
    issue_code: str | None = None,
) -> EvaluationRun:
    directory = Path("runs") / f"{run_number:03d}"
    return EvaluationRun(
        run_number=run_number,
        status=status,
        started_at=START + timedelta(seconds=run_number),
        ended_at=START + timedelta(seconds=run_number + 1),
        duration_ms=1000,
        action_count=action_count,
        trace_directory=directory,
        report_path=directory / "report.html",
        issue_code=issue_code,
    )


@pytest.mark.parametrize(
    ("observed_action", "kind"),
    [
        (action("fill", {"selector": "#search", "text": "query"}), DivergenceKind.ACTION_TYPE),
        (action(arguments={"selector": ".product:first-child"}), DivergenceKind.ARGUMENTS),
        (action(status=ActionStatus.FAILURE), DivergenceKind.EXECUTION_STATUS),
        (
            action(after_url="https://shop.example.test/wrong"),
            DivergenceKind.PAGE_URL,
        ),
        (
            action(
                state_after={
                    "url": "https://shop.example.test/product",
                    "title": "Wrong product",
                }
            ),
            DivergenceKind.STATE,
        ),
    ],
)
def test_finds_first_action_divergence(
    observed_action: ActionRecord,
    kind: DivergenceKind,
) -> None:
    divergence = compare_trajectories(
        verified_session([action()]),
        verified_session([observed_action], passed=False),
    )

    assert divergence is not None
    assert divergence.kind is kind
    assert divergence.action_number == 1


def test_ignores_browser_use_step_argument() -> None:
    baseline = action(arguments={"selector": "#product", "browser_use_step": 4})
    observed = action(arguments={"selector": "#product", "browser_use_step": 5})

    divergence = compare_trajectories(
        verified_session([baseline]),
        verified_session([observed], passed=False),
    )

    assert divergence is not None
    assert divergence.kind is DivergenceKind.FINAL_VERIFICATION


def test_detects_action_verification_divergence() -> None:
    passed = VerificationResult(
        expected_state="target is visible",
        observed_state="target is visible",
        passed=True,
    )
    failed = VerificationResult(
        expected_state="target is visible",
        observed_state="target is hidden",
        passed=False,
        failure_reason="target is hidden",
    )

    divergence = compare_trajectories(
        verified_session([action(verification=passed)]),
        verified_session([action(verification=failed)], passed=False),
    )

    assert divergence is not None
    assert divergence.kind is DivergenceKind.ACTION_VERIFICATION
    assert divergence.action_number == 1


def test_detects_browser_error_finding() -> None:
    event = {
        "event_type": "request_failed",
        "message": "Request failed",
        "url": "https://shop.example.test/api/products",
        "resource_type": "fetch",
    }

    divergence = compare_trajectories(
        verified_session([action()]),
        verified_session([action(browser_events=[event])], passed=False),
    )

    assert divergence is not None
    assert divergence.kind is DivergenceKind.BROWSER_ERROR
    assert divergence.action_number == 1


def test_detects_repeated_no_progress_finding() -> None:
    unchanged = {
        "url": "https://shop.example.test/search",
        "title": "Search",
    }
    observed_actions = [
        action(
            arguments={"selector": "#product", "browser_use_step": 4},
            before_url=unchanged["url"],
            state_after=unchanged,
        )
        for _ in range(3)
    ]
    baseline_actions = [
        action(
            arguments={"selector": "#product", "browser_use_step": step},
            before_url=unchanged["url"],
            state_after=unchanged,
        )
        for step in (1, 2, 3)
    ]

    divergence = compare_trajectories(
        verified_session(baseline_actions),
        verified_session(observed_actions, passed=False),
    )

    assert divergence is not None
    assert divergence.kind is DivergenceKind.TRAJECTORY_FINDING
    assert divergence.action_number == 1


def test_detects_final_verification_only_difference() -> None:
    divergence = compare_trajectories(
        verified_session([action()]),
        verified_session([action()], passed=False),
    )

    assert divergence is not None
    assert divergence.kind is DivergenceKind.FINAL_VERIFICATION
    assert divergence.action_number is None


def test_detects_missing_and_extra_actions() -> None:
    missing = compare_trajectories(
        verified_session([action(), action("press", {"selector": "#q", "key": "Enter"})]),
        verified_session([action()], passed=False),
    )
    extra = compare_trajectories(
        verified_session([action()]),
        verified_session([action(), action("click", {"selector": "#extra"})], passed=False),
    )

    assert missing is not None
    assert missing.kind is DivergenceKind.MISSING_ACTION
    assert missing.action_number == 2
    assert extra is not None
    assert extra.kind is DivergenceKind.EXTRA_ACTION
    assert extra.action_number == 2


def test_selects_median_success_and_groups_matching_failures() -> None:
    runs = (
        run(1, EvaluationRunStatus.PASSED, 2),
        run(2, EvaluationRunStatus.PASSED, 4),
        run(3, EvaluationRunStatus.PASSED, 8),
        run(4, EvaluationRunStatus.FAILED, 4),
        run(5, EvaluationRunStatus.FAILED, 4),
    )
    correct_actions = [action() for _ in range(4)]
    wrong_actions = [
        action() for _ in range(3)
    ] + [action(arguments={"selector": ".product:first-child"})]
    sessions = {
        1: verified_session(correct_actions[:2]),
        2: verified_session(correct_actions),
        3: verified_session(correct_actions + [action() for _ in range(4)]),
        4: verified_session(wrong_actions, passed=False),
        5: verified_session(wrong_actions, passed=False),
    }

    analyzed, representative, patterns = analyze_evaluation_runs(runs, sessions)

    assert representative == 2
    assert analyzed[3].divergence is not None
    assert analyzed[3].divergence.kind is DivergenceKind.ARGUMENTS
    assert analyzed[3].divergence.action_number == 4
    assert len(patterns) == 1
    assert patterns[0].run_numbers == (4, 5)
    assert patterns[0].representative_run_number == 4
    assert patterns[0].repeated


def test_no_success_baseline_groups_by_local_failure_reason() -> None:
    runs = (
        run(1, EvaluationRunStatus.FAILED, 1),
        run(2, EvaluationRunStatus.FAILED, 1),
    )
    sessions = {
        1: verified_session([action()], passed=False),
        2: verified_session([action()], passed=False),
    }

    analyzed, representative, patterns = analyze_evaluation_runs(runs, sessions)

    assert representative is None
    assert all(item.divergence is None for item in analyzed)
    assert len(patterns) == 1
    assert patterns[0].run_numbers == (1, 2)


def test_provider_issue_is_not_compared_as_agent_trajectory() -> None:
    runs = (
        run(1, EvaluationRunStatus.PASSED, 1),
        run(2, EvaluationRunStatus.UNVERIFIED, 1, "provider_rate_limited"),
        run(3, EvaluationRunStatus.UNVERIFIED, 1, "provider_rate_limited"),
        run(4, EvaluationRunStatus.UNVERIFIED, 1, "provider_timeout"),
    )
    sessions = {
        1: verified_session([action()]),
        2: verified_session([action("fill", {"text": "different"})]),
        3: verified_session([action("press", {"key": "Escape"})]),
        4: verified_session([action("click", {"selector": "#other"})]),
    }

    analyzed, representative, patterns = analyze_evaluation_runs(runs, sessions)

    assert representative == 1
    assert analyzed[1].divergence is None
    assert analyzed[2].divergence is None
    assert analyzed[3].divergence is None
    assert [pattern.run_numbers for pattern in patterns] == [(2, 3), (4,)]
    assert patterns[0].evidence["issue_code"] == "provider_rate_limited"
