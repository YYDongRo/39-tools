from __future__ import annotations

import re
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from statistics import fmean, median


class EvaluationRunStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNVERIFIED = "unverified"
    ERRORED = "errored"


class DivergenceKind(StrEnum):
    ACTION_TYPE = "action_type"
    ARGUMENTS = "arguments"
    EXECUTION_STATUS = "execution_status"
    ACTION_VERIFICATION = "action_verification"
    PAGE_URL = "page_url"
    BROWSER_ERROR = "browser_error"
    STATE = "state"
    TRAJECTORY_FINDING = "trajectory_finding"
    MISSING_ACTION = "missing_action"
    EXTRA_ACTION = "extra_action"
    FINAL_VERIFICATION = "final_verification"


@dataclass(frozen=True)
class TrajectoryDivergence:
    kind: DivergenceKind
    action_number: int | None
    summary: str
    baseline: dict[str, object] = field(default_factory=dict)
    observed: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DivergenceKind):
            raise TypeError("kind must be a DivergenceKind")
        if self.action_number is not None and (
            not isinstance(self.action_number, int)
            or isinstance(self.action_number, bool)
            or self.action_number <= 0
        ):
            raise ValueError("action_number must be a positive integer or None")
        _require_text(self.summary, "summary")


@dataclass(frozen=True)
class EvaluationRun:
    run_number: int
    status: EvaluationRunStatus
    started_at: datetime
    ended_at: datetime
    duration_ms: int
    action_count: int
    trace_directory: Path
    report_path: Path
    divergence: TrajectoryDivergence | None = None
    error_phase: str | None = None
    error_type: str | None = None

    def __post_init__(self) -> None:
        _require_positive_integer(self.run_number, "run_number")
        if not isinstance(self.status, EvaluationRunStatus):
            raise TypeError("status must be an EvaluationRunStatus")
        _validate_time_range(self.started_at, self.ended_at)
        _require_non_negative_integer(self.duration_ms, "duration_ms")
        _require_non_negative_integer(self.action_count, "action_count")
        _validate_relative_path(self.trace_directory, "trace_directory")
        _validate_relative_path(self.report_path, "report_path")
        if self.report_path != self.trace_directory / "report.html":
            raise ValueError("report_path must point to trace_directory/report.html")
        if self.divergence is not None and not isinstance(
            self.divergence,
            TrajectoryDivergence,
        ):
            raise TypeError("divergence must be a TrajectoryDivergence or None")
        if self.status is EvaluationRunStatus.ERRORED:
            _require_text(self.error_phase, "error_phase")
            _require_text(self.error_type, "error_type")
        elif self.error_phase is not None or self.error_type is not None:
            raise ValueError("only errored runs can contain error details")
        if self.status is EvaluationRunStatus.PASSED and self.divergence is not None:
            raise ValueError("passed runs cannot contain a divergence")


@dataclass(frozen=True)
class FailurePattern:
    pattern_id: str
    summary: str
    run_numbers: tuple[int, ...]
    representative_run_number: int
    divergence_kind: DivergenceKind | None = None
    action_number: int | None = None
    evidence: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.pattern_id, "pattern_id")
        _require_text(self.summary, "summary")
        if not self.run_numbers:
            raise ValueError("run_numbers cannot be empty")
        if tuple(sorted(set(self.run_numbers))) != self.run_numbers:
            raise ValueError("run_numbers must be sorted and unique")
        for run_number in self.run_numbers:
            _require_positive_integer(run_number, "run_number")
        if self.representative_run_number not in self.run_numbers:
            raise ValueError("representative run must belong to the pattern")
        if self.divergence_kind is not None and not isinstance(
            self.divergence_kind,
            DivergenceKind,
        ):
            raise TypeError("divergence_kind must be a DivergenceKind or None")
        if self.action_number is not None:
            _require_positive_integer(self.action_number, "action_number")

    @property
    def repeated(self) -> bool:
        return len(self.run_numbers) > 1


@dataclass(frozen=True)
class AgentEvaluation:
    evaluation_id: str
    task: str
    started_at: datetime
    ended_at: datetime
    requested_run_count: int
    runs: tuple[EvaluationRun, ...]
    output_dir: Path
    representative_success_run_number: int | None = None
    failure_patterns: tuple[FailurePattern, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.evaluation_id, "evaluation_id")
        _require_text(self.task, "task")
        _validate_time_range(self.started_at, self.ended_at)
        _require_positive_integer(
            self.requested_run_count,
            "requested_run_count",
        )
        if len(self.runs) > self.requested_run_count:
            raise ValueError("runs cannot exceed requested_run_count")
        expected_numbers = tuple(range(1, len(self.runs) + 1))
        if tuple(run.run_number for run in self.runs) != expected_numbers:
            raise ValueError("runs must be ordered consecutively from 1")
        if not isinstance(self.output_dir, Path):
            raise TypeError("output_dir must be a Path")
        if self.representative_success_run_number is not None:
            representative = self.run(self.representative_success_run_number)
            if representative.status is not EvaluationRunStatus.PASSED:
                raise ValueError("representative success must be a passed run")
        unsuccessful = {
            run.run_number
            for run in self.runs
            if run.status is not EvaluationRunStatus.PASSED
        }
        covered: set[int] = set()
        for pattern in self.failure_patterns:
            if not set(pattern.run_numbers) <= unsuccessful:
                raise ValueError("failure patterns can only reference unsuccessful runs")
            if covered.intersection(pattern.run_numbers):
                raise ValueError("an unsuccessful run cannot belong to two patterns")
            covered.update(pattern.run_numbers)

    def run(self, run_number: int) -> EvaluationRun:
        _require_positive_integer(run_number, "run_number")
        try:
            return self.runs[run_number - 1]
        except IndexError as error:
            raise ValueError(f"unknown run number: {run_number}") from error

    @property
    def report_path(self) -> Path:
        return self.output_dir / "report.html"

    @property
    def attempted_run_count(self) -> int:
        return len(self.runs)

    @property
    def passed_count(self) -> int:
        return self._count(EvaluationRunStatus.PASSED)

    @property
    def failed_count(self) -> int:
        return self._count(EvaluationRunStatus.FAILED)

    @property
    def unverified_count(self) -> int:
        return self._count(EvaluationRunStatus.UNVERIFIED)

    @property
    def errored_count(self) -> int:
        return self._count(EvaluationRunStatus.ERRORED)

    @property
    def completed_run_count(self) -> int:
        return self.attempted_run_count - self.errored_count

    @property
    def empirical_pass_rate(self) -> float:
        return self.passed_count / self.requested_run_count

    @property
    def all_runs_passed(self) -> bool:
        """Whether every requested run reached an explicit passed result."""

        return (
            self.attempted_run_count == self.requested_run_count
            and self.passed_count == self.requested_run_count
        )

    def assert_all_passed(self) -> None:
        """Raise an assertion suitable for CI when any run is not passed."""

        if self.all_runs_passed:
            return
        raise AssertionError(
            "Browser Use evaluation did not pass every requested run: "
            f"{self.passed_count}/{self.requested_run_count} passed, "
            f"{self.failed_count} failed, "
            f"{self.unverified_count} unverified, "
            f"{self.errored_count} errored. "
            f"Report: {self.report_path.resolve()}"
        )

    @property
    def average_duration_ms(self) -> float | None:
        values = [run.duration_ms for run in self._completed_runs]
        return fmean(values) if values else None

    @property
    def median_duration_ms(self) -> float | None:
        values = [run.duration_ms for run in self._completed_runs]
        return float(median(values)) if values else None

    @property
    def average_action_count(self) -> float | None:
        values = [run.action_count for run in self._completed_runs]
        return fmean(values) if values else None

    @property
    def median_action_count(self) -> float | None:
        values = [run.action_count for run in self._completed_runs]
        return float(median(values)) if values else None

    @property
    def representative_unsuccessful_run_numbers(self) -> tuple[int, ...]:
        return tuple(
            pattern.representative_run_number
            for pattern in self.failure_patterns
        )

    def open_report(self) -> Path:
        absolute_path = self.report_path.resolve()
        if not absolute_path.is_file():
            raise FileNotFoundError(f"report does not exist: {absolute_path}")
        if not webbrowser.open(absolute_path.as_uri(), new=2):
            raise RuntimeError(
                "could not open the report with the default browser; "
                f"open it manually: {absolute_path}"
            )
        return absolute_path

    @property
    def _completed_runs(self) -> tuple[EvaluationRun, ...]:
        return tuple(
            run
            for run in self.runs
            if run.status is not EvaluationRunStatus.ERRORED
        )

    def _count(self, status: EvaluationRunStatus) -> int:
        return sum(run.status is status for run in self.runs)


def _require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


def _require_positive_integer(value: object, field_name: str) -> None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
    ):
        raise ValueError(f"{field_name} must be a positive integer")


def _require_non_negative_integer(value: object, field_name: str) -> None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise ValueError(f"{field_name} must be a non-negative integer")


def _validate_time_range(started_at: datetime, ended_at: datetime) -> None:
    if not isinstance(started_at, datetime) or started_at.utcoffset() is None:
        raise ValueError("started_at must be a timezone-aware datetime")
    if not isinstance(ended_at, datetime) or ended_at.utcoffset() is None:
        raise ValueError("ended_at must be a timezone-aware datetime")
    if ended_at < started_at:
        raise ValueError("ended_at cannot be before started_at")


def _validate_relative_path(path: object, field_name: str) -> None:
    if not isinstance(path, Path):
        raise TypeError(f"{field_name} must be a Path")
    serialized = path.as_posix()
    posix_path = PurePosixPath(serialized)
    if (
        path.is_absolute()
        or posix_path.is_absolute()
        or ".." in path.parts
        or path == Path(".")
        or "\\" in serialized
        or re.match(r"^[A-Za-z]:/", serialized) is not None
    ):
        raise ValueError(f"{field_name} must be a safe relative path")


__all__ = [
    "AgentEvaluation",
    "DivergenceKind",
    "EvaluationRun",
    "EvaluationRunStatus",
    "FailurePattern",
    "TrajectoryDivergence",
]
