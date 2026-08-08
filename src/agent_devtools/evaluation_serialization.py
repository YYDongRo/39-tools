from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from agent_devtools.evaluation import (
    AgentEvaluation,
    DivergenceKind,
    EvaluationRun,
    EvaluationRunStatus,
    FailurePattern,
    TrajectoryDivergence,
)
from agent_devtools.serialization import _write_json


EVALUATION_SCHEMA_VERSION = 1


def evaluation_to_dict(evaluation: AgentEvaluation) -> dict[str, object]:
    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "evaluation_id": evaluation.evaluation_id,
        "task": evaluation.task,
        "started_at": _timestamp(evaluation.started_at),
        "ended_at": _timestamp(evaluation.ended_at),
        "requested_run_count": evaluation.requested_run_count,
        "summary": _summary_to_dict(evaluation),
        "representative_success_run_number": (
            evaluation.representative_success_run_number
        ),
        "runs": [_run_to_dict(run) for run in evaluation.runs],
        "failure_patterns": [
            _pattern_to_dict(pattern)
            for pattern in evaluation.failure_patterns
        ],
    }


def evaluation_from_dict(
    data: dict[str, object],
    *,
    output_dir: Path,
) -> AgentEvaluation:
    if data.get("schema_version") != EVALUATION_SCHEMA_VERSION:
        raise ValueError(
            "unsupported evaluation schema_version: "
            f"{data.get('schema_version')!r}"
        )

    evaluation = AgentEvaluation(
        evaluation_id=_text(data, "evaluation_id"),
        task=_text(data, "task"),
        started_at=_datetime(data, "started_at"),
        ended_at=_datetime(data, "ended_at"),
        requested_run_count=_integer(data, "requested_run_count"),
        runs=tuple(
            _run_from_dict(value, index)
            for index, value in enumerate(_array(data, "runs"))
        ),
        output_dir=output_dir,
        representative_success_run_number=_optional_integer(
            data,
            "representative_success_run_number",
        ),
        failure_patterns=tuple(
            _pattern_from_dict(value, index)
            for index, value in enumerate(_array(data, "failure_patterns"))
        ),
    )
    summary = data.get("summary")
    if summary != _summary_to_dict(evaluation):
        raise ValueError("evaluation summary does not match its runs")
    return evaluation


def write_evaluation_json(
    evaluation: AgentEvaluation,
    output_path: Path,
) -> None:
    _write_json(evaluation_to_dict(evaluation), output_path)


def read_evaluation_json(input_path: Path) -> AgentEvaluation:
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid evaluation JSON: {error.msg}") from error
    if not isinstance(data, dict):
        raise ValueError("evaluation JSON must contain an object")
    return evaluation_from_dict(data, output_dir=input_path.parent)


def _run_to_dict(run: EvaluationRun) -> dict[str, object]:
    data: dict[str, object] = {
        "run_number": run.run_number,
        "status": run.status.value,
        "started_at": _timestamp(run.started_at),
        "ended_at": _timestamp(run.ended_at),
        "duration_ms": run.duration_ms,
        "action_count": run.action_count,
        "trace_directory": run.trace_directory.as_posix(),
        "report_path": run.report_path.as_posix(),
        "divergence": _divergence_to_dict(run.divergence),
        "error_phase": run.error_phase,
        "error_type": run.error_type,
    }
    if run.issue_code is not None:
        data["issue_code"] = run.issue_code
    return data


def _run_from_dict(value: object, index: int) -> EvaluationRun:
    data = _object(value, f"run at index {index}")
    try:
        status = EvaluationRunStatus(_text(data, "status"))
    except ValueError as error:
        raise ValueError(f"invalid run status at index {index}") from error
    issue_code = _optional_text_if_present(data, "issue_code")
    return EvaluationRun(
        run_number=_integer(data, "run_number"),
        status=status,
        started_at=_datetime(data, "started_at"),
        ended_at=_datetime(data, "ended_at"),
        duration_ms=_integer(data, "duration_ms"),
        action_count=_integer(data, "action_count"),
        trace_directory=_relative_path(data, "trace_directory"),
        report_path=_relative_path(data, "report_path"),
        divergence=_divergence_from_dict(data.get("divergence")),
        error_phase=_optional_text(data, "error_phase"),
        error_type=_optional_text(data, "error_type"),
        issue_code=issue_code,
    )


def _divergence_to_dict(
    divergence: TrajectoryDivergence | None,
) -> dict[str, object] | None:
    if divergence is None:
        return None
    return {
        "kind": divergence.kind.value,
        "action_number": divergence.action_number,
        "summary": divergence.summary,
        "baseline": divergence.baseline,
        "observed": divergence.observed,
    }


def _divergence_from_dict(value: object) -> TrajectoryDivergence | None:
    if value is None:
        return None
    data = _object(value, "divergence")
    try:
        kind = DivergenceKind(_text(data, "kind"))
    except ValueError as error:
        raise ValueError("invalid divergence kind") from error
    return TrajectoryDivergence(
        kind=kind,
        action_number=_optional_integer(data, "action_number"),
        summary=_text(data, "summary"),
        baseline=_string_keyed_object(data, "baseline"),
        observed=_string_keyed_object(data, "observed"),
    )


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


def _pattern_from_dict(value: object, index: int) -> FailurePattern:
    data = _object(value, f"failure pattern at index {index}")
    kind_value = _optional_text(data, "divergence_kind")
    try:
        kind = DivergenceKind(kind_value) if kind_value is not None else None
    except ValueError as error:
        raise ValueError(f"invalid failure pattern kind at index {index}") from error
    run_numbers_value = _array(data, "run_numbers")
    run_numbers = tuple(
        _plain_integer(value, f"run_numbers[{number_index}]")
        for number_index, value in enumerate(run_numbers_value)
    )
    return FailurePattern(
        pattern_id=_text(data, "pattern_id"),
        summary=_text(data, "summary"),
        run_numbers=run_numbers,
        representative_run_number=_integer(
            data,
            "representative_run_number",
        ),
        divergence_kind=kind,
        action_number=_optional_integer(data, "action_number"),
        evidence=_string_keyed_object(data, "evidence"),
    )


def _summary_to_dict(evaluation: AgentEvaluation) -> dict[str, object]:
    return {
        "attempted_run_count": evaluation.attempted_run_count,
        "completed_run_count": evaluation.completed_run_count,
        "passed_count": evaluation.passed_count,
        "failed_count": evaluation.failed_count,
        "unverified_count": evaluation.unverified_count,
        "errored_count": evaluation.errored_count,
        "empirical_pass_rate": evaluation.empirical_pass_rate,
        "average_duration_ms": evaluation.average_duration_ms,
        "median_duration_ms": evaluation.median_duration_ms,
        "average_action_count": evaluation.average_action_count,
        "median_action_count": evaluation.median_action_count,
    }


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise ValueError(f"{label} must be an object with string keys")
    return value


def _string_keyed_object(data: dict[str, object], field: str) -> dict[str, object]:
    if field not in data:
        raise ValueError(f"missing required evaluation field: {field}")
    return dict(_object(data[field], field))


def _array(data: dict[str, object], field: str) -> list[object]:
    try:
        value = data[field]
    except KeyError as error:
        raise ValueError(f"missing required evaluation field: {field}") from error
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


def _text(data: dict[str, object], field: str) -> str:
    try:
        value = data[field]
    except KeyError as error:
        raise ValueError(f"missing required evaluation field: {field}") from error
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value


def _optional_text(data: dict[str, object], field: str) -> str | None:
    try:
        value = data[field]
    except KeyError as error:
        raise ValueError(f"missing required evaluation field: {field}") from error
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{field} must be a string or null")
    return value


def _optional_text_if_present(
    data: dict[str, object],
    field: str,
) -> str | None:
    value = data.get(field)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{field} must be a string or null")
    return value


def _plain_integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    return value


def _integer(data: dict[str, object], field: str) -> int:
    try:
        value = data[field]
    except KeyError as error:
        raise ValueError(f"missing required evaluation field: {field}") from error
    return _plain_integer(value, field)


def _optional_integer(data: dict[str, object], field: str) -> int | None:
    try:
        value = data[field]
    except KeyError as error:
        raise ValueError(f"missing required evaluation field: {field}") from error
    if value is None:
        return None
    return _plain_integer(value, field)


def _datetime(data: dict[str, object], field: str) -> datetime:
    value = _text(data, field)
    try:
        result = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be a valid ISO 8601 timestamp") from error
    if result.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return result.astimezone(UTC)


def _relative_path(data: dict[str, object], field: str) -> Path:
    value = _text(data, field)
    if "\\" in value:
        raise ValueError(f"{field} must use POSIX separators")
    path = Path(value)
    posix_path = PurePosixPath(value)
    if (
        posix_path.is_absolute()
        or ".." in path.parts
        or path == Path(".")
        or re.match(r"^[A-Za-z]:/", value) is not None
    ):
        raise ValueError(f"{field} must be a safe relative path")
    return path


__all__ = [
    "EVALUATION_SCHEMA_VERSION",
    "evaluation_from_dict",
    "evaluation_to_dict",
    "read_evaluation_json",
    "write_evaluation_json",
]
