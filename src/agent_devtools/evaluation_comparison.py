"""Compare repeated evaluations of the same agent task."""

from __future__ import annotations

import json

from agent_devtools.evaluation import (
    AgentEvaluation,
    EvaluationComparison,
    EvaluationComparisonStatus,
    EvaluationStatusCounts,
    FailurePattern,
)


def compare_evaluations(
    baseline: AgentEvaluation,
    current: AgentEvaluation,
) -> EvaluationComparison:
    """Compare two evaluations without treating a changed task as a regression."""

    baseline_counts = EvaluationStatusCounts.from_evaluation(baseline)
    current_counts = EvaluationStatusCounts.from_evaluation(current)
    if baseline.task != current.task:
        return EvaluationComparison(
            comparison_id=_comparison_id(baseline, current),
            task=current.task,
            baseline_evaluation_id=baseline.evaluation_id,
            current_evaluation_id=current.evaluation_id,
            status=EvaluationComparisonStatus.INCOMPARABLE,
            baseline_counts=baseline_counts,
            current_counts=current_counts,
            baseline_pass_rate=baseline.empirical_pass_rate,
            current_pass_rate=current.empirical_pass_rate,
            baseline_average_duration_ms=baseline.average_duration_ms,
            current_average_duration_ms=current.average_duration_ms,
            baseline_average_action_count=baseline.average_action_count,
            current_average_action_count=current.average_action_count,
            reason="The task text changed, so these evaluations are not comparable.",
        )

    new_patterns, resolved_patterns = _pattern_changes(baseline, current)
    status = _comparison_status(
        baseline,
        current,
        new_pattern_count=len(new_patterns),
        resolved_pattern_count=len(resolved_patterns),
    )
    return EvaluationComparison(
        comparison_id=_comparison_id(baseline, current),
        task=current.task,
        baseline_evaluation_id=baseline.evaluation_id,
        current_evaluation_id=current.evaluation_id,
        status=status,
        baseline_counts=baseline_counts,
        current_counts=current_counts,
        baseline_pass_rate=baseline.empirical_pass_rate,
        current_pass_rate=current.empirical_pass_rate,
        baseline_average_duration_ms=baseline.average_duration_ms,
        current_average_duration_ms=current.average_duration_ms,
        baseline_average_action_count=baseline.average_action_count,
        current_average_action_count=current.average_action_count,
        new_patterns=new_patterns,
        resolved_patterns=resolved_patterns,
    )


def _comparison_id(
    baseline: AgentEvaluation,
    current: AgentEvaluation,
) -> str:
    return f"{baseline.evaluation_id}-vs-{current.evaluation_id}"


def _pattern_changes(
    baseline: AgentEvaluation,
    current: AgentEvaluation,
) -> tuple[tuple[FailurePattern, ...], tuple[FailurePattern, ...]]:
    baseline_patterns = {
        _pattern_signature(pattern): pattern
        for pattern in baseline.failure_patterns
    }
    current_patterns = {
        _pattern_signature(pattern): pattern
        for pattern in current.failure_patterns
    }
    new_patterns = tuple(
        pattern
        for signature, pattern in current_patterns.items()
        if signature not in baseline_patterns
    )
    resolved_patterns = tuple(
        pattern
        for signature, pattern in baseline_patterns.items()
        if signature not in current_patterns
    )
    return new_patterns, resolved_patterns


def _pattern_signature(pattern: FailurePattern) -> str:
    """Ignore generated pattern IDs and run numbers when matching patterns."""

    return json.dumps(
        {
            "summary": pattern.summary,
            "divergence_kind": (
                pattern.divergence_kind.value
                if pattern.divergence_kind is not None
                else None
            ),
            "action_number": pattern.action_number,
            "evidence": pattern.evidence,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _comparison_status(
    baseline: AgentEvaluation,
    current: AgentEvaluation,
    *,
    new_pattern_count: int,
    resolved_pattern_count: int,
) -> EvaluationComparisonStatus:
    if current.empirical_pass_rate > baseline.empirical_pass_rate:
        return EvaluationComparisonStatus.IMPROVED
    if current.empirical_pass_rate < baseline.empirical_pass_rate:
        return EvaluationComparisonStatus.REGRESSED

    baseline_hard_failures = baseline.failed_count + baseline.errored_count
    current_hard_failures = current.failed_count + current.errored_count
    if current_hard_failures < baseline_hard_failures:
        return EvaluationComparisonStatus.IMPROVED
    if current_hard_failures > baseline_hard_failures:
        return EvaluationComparisonStatus.REGRESSED
    if current.unverified_count < baseline.unverified_count:
        return EvaluationComparisonStatus.IMPROVED
    if current.unverified_count > baseline.unverified_count:
        return EvaluationComparisonStatus.REGRESSED
    if new_pattern_count < resolved_pattern_count:
        return EvaluationComparisonStatus.IMPROVED
    if new_pattern_count > resolved_pattern_count:
        return EvaluationComparisonStatus.REGRESSED
    return EvaluationComparisonStatus.UNCHANGED


__all__ = ["compare_evaluations"]
