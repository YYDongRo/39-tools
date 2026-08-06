"""Versioned JSON persistence for evaluation comparisons."""

from __future__ import annotations

import json
from pathlib import Path

from agent_devtools.evaluation import (
    DivergenceKind,
    EvaluationComparison,
    EvaluationComparisonStatus,
    EvaluationStatusCounts,
    FailurePattern,
)
from agent_devtools.serialization import _write_json


COMPARISON_SCHEMA_VERSION = 1


def comparison_to_dict(comparison: EvaluationComparison) -> dict[str, object]:
    return {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "comparison_id": comparison.comparison_id,
        "task": comparison.task,
        "baseline_evaluation_id": comparison.baseline_evaluation_id,
        "current_evaluation_id": comparison.current_evaluation_id,
        "status": comparison.status.value,
        "summary": comparison.summary,
        "baseline": _side_to_dict(
            comparison.baseline_counts,
            comparison.baseline_pass_rate,
            comparison.baseline_average_duration_ms,
            comparison.baseline_average_action_count,
        ),
        "current": _side_to_dict(
            comparison.current_counts,
            comparison.current_pass_rate,
            comparison.current_average_duration_ms,
            comparison.current_average_action_count,
        ),
        "pass_rate_delta": comparison.pass_rate_delta,
        "new_patterns": [
            _pattern_to_dict(pattern) for pattern in comparison.new_patterns
        ],
        "resolved_patterns": [
            _pattern_to_dict(pattern)
            for pattern in comparison.resolved_patterns
        ],
        "reason": comparison.reason,
    }


def comparison_from_dict(data: dict[str, object]) -> EvaluationComparison:
    if data.get("schema_version") != COMPARISON_SCHEMA_VERSION:
        raise ValueError(
            "unsupported comparison schema_version: "
            f"{data.get('schema_version')!r}"
        )
    try:
        status = EvaluationComparisonStatus(_text(data, "status"))
    except ValueError as error:
        raise ValueError("invalid comparison status") from error
    baseline = _object(data.get("baseline"), "baseline")
    current = _object(data.get("current"), "current")
    comparison = EvaluationComparison(
        comparison_id=_text(data, "comparison_id"),
        task=_text(data, "task"),
        baseline_evaluation_id=_text(data, "baseline_evaluation_id"),
        current_evaluation_id=_text(data, "current_evaluation_id"),
        status=status,
        baseline_counts=_counts(baseline),
        current_counts=_counts(current),
        baseline_pass_rate=_number(baseline, "pass_rate"),
        current_pass_rate=_number(current, "pass_rate"),
        baseline_average_duration_ms=_optional_number(
            baseline,
            "average_duration_ms",
        ),
        current_average_duration_ms=_optional_number(
            current,
            "average_duration_ms",
        ),
        baseline_average_action_count=_optional_number(
            baseline,
            "average_action_count",
        ),
        current_average_action_count=_optional_number(
            current,
            "average_action_count",
        ),
        new_patterns=tuple(
            _pattern(value, index)
            for index, value in enumerate(_array(data, "new_patterns"))
        ),
        resolved_patterns=tuple(
            _pattern(value, index)
            for index, value in enumerate(_array(data, "resolved_patterns"))
        ),
        reason=_optional_text(data, "reason"),
    )
    if data.get("summary") != comparison.summary:
        raise ValueError("comparison summary does not match its status")
    if data.get("pass_rate_delta") != comparison.pass_rate_delta:
        raise ValueError("comparison pass_rate_delta does not match its sides")
    return comparison


def write_evaluation_comparison_json(
    comparison: EvaluationComparison,
    output_path: Path,
) -> None:
    _write_json(comparison_to_dict(comparison), output_path)


def read_evaluation_comparison_json(input_path: Path) -> EvaluationComparison:
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid comparison JSON: {error.msg}") from error
    if not isinstance(data, dict):
        raise ValueError("comparison JSON must contain an object")
    return comparison_from_dict(data)


def _side_to_dict(
    counts: EvaluationStatusCounts,
    pass_rate: float,
    average_duration_ms: float | None,
    average_action_count: float | None,
) -> dict[str, object]:
    return {
        "counts": counts.to_dict(),
        "pass_rate": pass_rate,
        "average_duration_ms": average_duration_ms,
        "average_action_count": average_action_count,
    }


def _pattern_to_dict(pattern: FailurePattern) -> dict[str, object]:
    return {
        "pattern_id": pattern.pattern_id,
        "summary": pattern.summary,
        "run_numbers": list(pattern.run_numbers),
        "representative_run_number": pattern.representative_run_number,
        "divergence_kind": (
            pattern.divergence_kind.value
            if pattern.divergence_kind is not None
            else None
        ),
        "action_number": pattern.action_number,
        "evidence": pattern.evidence,
    }


def _pattern(value: object, index: int) -> FailurePattern:
    data = _object(value, f"pattern at index {index}")
    kind_value = _optional_text(data, "divergence_kind")
    try:
        kind = DivergenceKind(kind_value) if kind_value is not None else None
    except ValueError as error:
        raise ValueError(f"invalid pattern divergence_kind at index {index}") from error
    return FailurePattern(
        pattern_id=_text(data, "pattern_id"),
        summary=_text(data, "summary"),
        run_numbers=tuple(
            _plain_integer(value, "run_number")
            for value in _array(data, "run_numbers")
        ),
        representative_run_number=_integer(data, "representative_run_number"),
        divergence_kind=kind,
        action_number=_optional_integer(data, "action_number"),
        evidence=_string_keyed_object(data, "evidence"),
    )


def _counts(data: dict[str, object]) -> EvaluationStatusCounts:
    counts = _object(data.get("counts"), "counts")
    return EvaluationStatusCounts(
        passed=_integer(counts, "passed"),
        failed=_integer(counts, "failed"),
        unverified=_integer(counts, "unverified"),
        errored=_integer(counts, "errored"),
    )


def _object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise ValueError(f"{field} must be an object with string keys")
    return value


def _array(data: dict[str, object], field: str) -> list[object]:
    value = data.get(field)
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


def _string_keyed_object(
    data: dict[str, object],
    field: str,
) -> dict[str, object]:
    return dict(_object(data.get(field), field))


def _text(data: dict[str, object], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _optional_text(data: dict[str, object], field: str) -> str | None:
    value = data.get(field)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{field} must be a string or null")
    return value


def _integer(data: dict[str, object], field: str) -> int:
    return _plain_integer(data.get(field), field)


def _optional_integer(data: dict[str, object], field: str) -> int | None:
    value = data.get(field)
    if value is None:
        return None
    return _plain_integer(value, field)


def _plain_integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    return value


def _number(data: dict[str, object], field: str) -> float:
    value = data.get(field)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
    ):
        raise ValueError(f"{field} must be a number")
    return float(value)


def _optional_number(data: dict[str, object], field: str) -> float | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{field} must be a number or null")
    return float(value)


__all__ = [
    "COMPARISON_SCHEMA_VERSION",
    "comparison_from_dict",
    "comparison_to_dict",
    "read_evaluation_comparison_json",
    "write_evaluation_comparison_json",
]
