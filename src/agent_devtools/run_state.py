"""A small, local status contract for the future Agent DevTools UI."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from uuid import uuid4


RUN_STATE_SCHEMA_VERSION = 1


class RunStateStatus(StrEnum):
    """UI-facing lifecycle and final-result states.

    This status is intentionally separate from action execution status and
    task verification models.  ``TRACKING`` means that an observer is active;
    it does not mean that the task has succeeded.
    """

    NOT_CONFIGURED = "not_configured"
    READY = "ready"
    TRACKING = "tracking"
    PASSED = "passed"
    FAILED = "failed"
    UNVERIFIED = "unverified"
    ERRORED = "errored"


@dataclass(frozen=True)
class RunState:
    """The sanitized state that a local UI can read while a run progresses."""

    status: RunStateStatus
    updated_at: datetime
    run_id: str | None = None
    task: str | None = None
    started_at: datetime | None = None
    action_count: int = 0
    report_path: Path | None = None
    issue_code: str | None = None
    error_type: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, RunStateStatus):
            raise TypeError("status must be a RunStateStatus")
        _validate_timestamp(self.updated_at, "updated_at")
        if self.started_at is not None:
            _validate_timestamp(self.started_at, "started_at")
            if self.started_at > self.updated_at:
                raise ValueError("started_at cannot be later than updated_at")
        if not isinstance(self.action_count, int) or isinstance(
            self.action_count, bool
        ):
            raise TypeError("action_count must be an integer")
        if self.action_count < 0:
            raise ValueError("action_count cannot be negative")

        _validate_optional_text(self.run_id, "run_id")
        _validate_optional_text(self.task, "task")
        _validate_optional_text(self.issue_code, "issue_code")
        _validate_optional_text(self.error_type, "error_type")
        if self.report_path is not None:
            _validate_relative_path(self.report_path)

        if self.status in {RunStateStatus.NOT_CONFIGURED, RunStateStatus.READY}:
            if any(
                value is not None
                for value in (self.run_id, self.task, self.started_at)
            ):
                raise ValueError(
                    f"{self.status.value} state cannot describe an active run"
                )
            if self.action_count != 0 or self.report_path is not None:
                raise ValueError(
                    f"{self.status.value} state cannot contain run data"
                )

        if self.status is RunStateStatus.TRACKING:
            if self.run_id is None or self.started_at is None:
                raise ValueError(
                    "tracking state requires run_id and started_at"
                )
            if self.report_path is not None:
                raise ValueError("tracking state cannot have a report path")

        if self.status in {
            RunStateStatus.PASSED,
            RunStateStatus.FAILED,
            RunStateStatus.UNVERIFIED,
            RunStateStatus.ERRORED,
        } and self.run_id is None:
            raise ValueError(f"{self.status.value} state requires run_id")

        if self.status is RunStateStatus.ERRORED:
            if self.error_type is None and self.issue_code is None:
                raise ValueError(
                    "errored state requires error_type or issue_code"
                )
        elif self.error_type is not None:
            raise ValueError("error_type is only valid for errored state")


class _RunStateReporter:
    """Best-effort state updates shared by the recording integrations."""

    def __init__(
        self,
        state_path: str | Path | None,
        output_dir: str | Path,
        task: str | None,
        *,
        started_at: datetime | None = None,
    ) -> None:
        self._state_path = Path(state_path) if state_path is not None else None
        self._output_dir = Path(output_dir)
        self._report_path = self._output_dir / "report.html"
        self._run_id = self._output_dir.name or f"run-{uuid4().hex[:8]}"
        self._task = task
        self._started_at = started_at or datetime.now(UTC)
        self._report_relative_path = self._relative_report_path()
        self.publish(RunStateStatus.TRACKING, action_count=0)

    def publish(
        self,
        status: RunStateStatus,
        *,
        action_count: int,
        issue_code: str | None = None,
        error_type: str | None = None,
    ) -> None:
        if self._state_path is None:
            return
        state = RunState(
            status=status,
            updated_at=datetime.now(UTC),
            run_id=self._run_id,
            task=self._task,
            started_at=self._started_at,
            action_count=action_count,
            report_path=(
                self._report_relative_path
                if status is not RunStateStatus.TRACKING
                else None
            ),
            issue_code=issue_code,
            error_type=error_type,
        )
        try:
            write_run_state(state, self._state_path)
        except Exception:
            # Run-state reporting is auxiliary and must not change agent
            # behavior when its local file cannot be written.
            return

    def finish(
        self,
        session: object,
        *,
        exception: BaseException | None = None,
        error_type: str | None = None,
        issue_code: str | None = None,
    ) -> None:
        action_count = len(getattr(session, "actions", ()))
        session_issue_code = _session_issue_code(session)
        if exception is not None or error_type is not None:
            self.publish(
                RunStateStatus.ERRORED,
                action_count=action_count,
                issue_code=issue_code or session_issue_code,
                error_type=error_type or type(exception).__name__,
            )
            return

        verification = getattr(session, "verification", None)
        if verification is None:
            self.publish(
                RunStateStatus.UNVERIFIED,
                action_count=action_count,
                issue_code=issue_code or session_issue_code,
            )
            return

        status = (
            RunStateStatus.PASSED
            if verification.passed
            else RunStateStatus.FAILED
        )
        self.publish(
            status,
            action_count=action_count,
            issue_code=issue_code or session_issue_code,
        )

    def update_action_count(self, action_count: int) -> None:
        self.publish(RunStateStatus.TRACKING, action_count=action_count)

    def _relative_report_path(self) -> Path | None:
        if self._state_path is None:
            return None
        try:
            report = self._report_path.resolve()
            state_root = self._state_path.parent.resolve()
            relative = report.relative_to(state_root)
        except (OSError, ValueError):
            return None
        try:
            return _relative_path_from_value(
                relative.as_posix(),
                "report_path",
            )
        except ValueError:
            return None


def _session_issue_code(session: object) -> str | None:
    value = getattr(session, "issue_code", None)
    if isinstance(value, str) and value.strip():
        return value
    verification = getattr(session, "verification", None)
    category = getattr(verification, "failure_category", None)
    value = getattr(category, "value", None)
    return value if isinstance(value, str) and value.strip() else None


def run_state_to_dict(state: RunState) -> dict[str, object]:
    """Return the versioned, JSON-safe representation of ``state``."""

    return {
        "schema_version": RUN_STATE_SCHEMA_VERSION,
        "status": state.status.value,
        "updated_at": _timestamp_text(state.updated_at),
        "run_id": state.run_id,
        "task": state.task,
        "started_at": (
            _timestamp_text(state.started_at)
            if state.started_at is not None
            else None
        ),
        "action_count": state.action_count,
        "report_path": (
            state.report_path.as_posix()
            if state.report_path is not None
            else None
        ),
        "issue_code": state.issue_code,
        # Store only a type name, never an exception message or traceback.
        "error_type": state.error_type,
    }


def run_state_from_dict(data: object) -> RunState:
    """Validate and load a versioned run-state object."""

    if not isinstance(data, dict):
        raise ValueError("run state must be a JSON object")
    schema_version = data.get("schema_version")
    if schema_version != RUN_STATE_SCHEMA_VERSION:
        raise ValueError(f"unsupported run state schema: {schema_version!r}")

    required = (
        "status",
        "updated_at",
        "run_id",
        "task",
        "started_at",
        "action_count",
        "report_path",
        "issue_code",
        "error_type",
    )
    for field_name in required:
        if field_name not in data:
            raise ValueError(f"missing required run state field: {field_name}")

    status_value = data["status"]
    if not isinstance(status_value, str):
        raise ValueError("run state status must be a string")
    try:
        status = RunStateStatus(status_value)
    except ValueError as error:
        raise ValueError(f"invalid run state status: {status_value!r}") from error

    updated_at = _timestamp_from_value(data["updated_at"], "updated_at")
    started_at_value = data["started_at"]
    started_at = (
        None
        if started_at_value is None
        else _timestamp_from_value(started_at_value, "started_at")
    )

    action_count = data["action_count"]
    if not isinstance(action_count, int) or isinstance(action_count, bool):
        raise ValueError("run state action_count must be an integer")

    report_path_value = data["report_path"]
    report_path = (
        None
        if report_path_value is None
        else _relative_path_from_value(report_path_value, "report_path")
    )

    return RunState(
        status=status,
        updated_at=updated_at,
        run_id=_optional_text_from_value(data["run_id"], "run_id"),
        task=_optional_text_from_value(data["task"], "task"),
        started_at=started_at,
        action_count=action_count,
        report_path=report_path,
        issue_code=_optional_text_from_value(data["issue_code"], "issue_code"),
        error_type=_optional_text_from_value(data["error_type"], "error_type"),
    )


def write_run_state(state: RunState, output_path: str | Path) -> Path:
    """Atomically write ``state`` and return the output path."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(
                json.dumps(
                    run_state_to_dict(state),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return path


def read_run_state(input_path: str | Path) -> RunState:
    """Read and validate a persisted run state."""

    path = Path(input_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid run state JSON: {path}") from error
    return run_state_from_dict(data)


def _validate_timestamp(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _timestamp_text(value: datetime) -> str:
    _validate_timestamp(value, "timestamp")
    return value.astimezone(UTC).isoformat()


def _timestamp_from_value(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid ISO 8601 timestamp") from error
    _validate_timestamp(parsed, field_name)
    return parsed.astimezone(UTC)


def _validate_optional_text(value: str | None, field_name: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{field_name} must be a non-empty string or None")


def _optional_text_from_value(value: object, field_name: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string or null")
    _validate_optional_text(value, field_name)
    return value


def _validate_relative_path(value: Path) -> None:
    _relative_path_from_value(value.as_posix(), "report_path")


def _relative_path_from_value(value: object, field_name: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty path or null")
    if "\\" in value:
        raise ValueError(f"{field_name} must use POSIX separators")
    path = Path(value)
    posix_path = PurePosixPath(value)
    if (
        posix_path.is_absolute()
        or ".." in posix_path.parts
        or path == Path(".")
        or re.match(r"^[A-Za-z]:/", value) is not None
    ):
        raise ValueError(f"{field_name} must be a safe relative path")
    return path


__all__ = [
    "RUN_STATE_SCHEMA_VERSION",
    "RunState",
    "RunStateStatus",
    "read_run_state",
    "run_state_from_dict",
    "run_state_to_dict",
    "write_run_state",
]
