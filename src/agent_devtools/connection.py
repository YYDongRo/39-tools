"""A small local handshake between an observer and the control center."""

from __future__ import annotations

import atexit
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4


CONNECTION_STATE_SCHEMA_VERSION = 1
CONNECTION_STATE_FILENAME = "connection-state.json"


class ConnectionStatus(StrEnum):
    """Lifecycle state persisted for one observer process."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True)
class ConnectionState:
    """Sanitized, local-only information about an observer registration."""

    status: ConnectionStatus
    updated_at: datetime
    connection_id: str
    observer_kind: str
    process_id: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ConnectionStatus):
            raise TypeError("status must be a ConnectionStatus")
        if not isinstance(self.updated_at, datetime):
            raise TypeError("updated_at must be a datetime")
        if self.updated_at.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")
        for value, field_name in (
            (self.connection_id, "connection_id"),
            (self.observer_kind, "observer_kind"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
            if len(value) > 128:
                raise ValueError(f"{field_name} is too long")
        if self.process_id is not None:
            if not isinstance(self.process_id, int) or isinstance(
                self.process_id, bool
            ):
                raise TypeError("process_id must be an integer or None")
            if self.process_id <= 0:
                raise ValueError("process_id must be positive or None")


def connection_state_to_dict(state: ConnectionState) -> dict[str, object]:
    """Return the versioned JSON representation of a connection state."""

    return {
        "schema_version": CONNECTION_STATE_SCHEMA_VERSION,
        "status": state.status.value,
        "updated_at": state.updated_at.astimezone(UTC).isoformat(),
        "connection_id": state.connection_id,
        "observer_kind": state.observer_kind,
        "process_id": state.process_id,
    }


def connection_state_from_dict(data: object) -> ConnectionState:
    """Validate and load a persisted connection state."""

    if not isinstance(data, dict):
        raise ValueError("connection state must be a JSON object")
    if data.get("schema_version") != CONNECTION_STATE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported connection state schema: {data.get('schema_version')!r}"
        )
    required = (
        "status",
        "updated_at",
        "connection_id",
        "observer_kind",
        "process_id",
    )
    for field_name in required:
        if field_name not in data:
            raise ValueError(
                f"missing required connection state field: {field_name}"
            )

    status_value = data["status"]
    if not isinstance(status_value, str):
        raise ValueError("connection state status must be a string")
    try:
        status = ConnectionStatus(status_value)
    except ValueError as error:
        raise ValueError(
            f"invalid connection state status: {status_value!r}"
        ) from error

    timestamp_value = data["updated_at"]
    if not isinstance(timestamp_value, str):
        raise ValueError("updated_at must be an ISO 8601 string")
    try:
        updated_at = datetime.fromisoformat(timestamp_value)
    except ValueError as error:
        raise ValueError("updated_at must be a valid ISO 8601 timestamp") from error
    if updated_at.utcoffset() is None:
        raise ValueError("updated_at must be timezone-aware")

    process_id = data["process_id"]
    if process_id is not None and (
        not isinstance(process_id, int) or isinstance(process_id, bool)
    ):
        raise ValueError("process_id must be an integer or null")
    return ConnectionState(
        status=status,
        updated_at=updated_at.astimezone(UTC),
        connection_id=_required_text(data["connection_id"], "connection_id"),
        observer_kind=_required_text(data["observer_kind"], "observer_kind"),
        process_id=process_id,
    )


def write_connection_state(
    state: ConnectionState,
    output_path: str | Path,
) -> Path:
    """Atomically write a connection state and return its path."""

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
                    connection_state_to_dict(state),
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


def read_connection_state(input_path: str | Path) -> ConnectionState:
    """Read and validate a persisted connection state."""

    path = Path(input_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid connection state JSON: {path}") from error
    return connection_state_from_dict(data)


class ConnectionReporter:
    """Best-effort registration and liveness marker for an observer process."""

    def __init__(
        self,
        output_root: str | Path,
        *,
        observer_kind: str,
    ) -> None:
        if not isinstance(observer_kind, str) or not observer_kind.strip():
            raise ValueError("observer_kind must be a non-empty string")
        self.path = Path(output_root) / CONNECTION_STATE_FILENAME
        self.connection_id = uuid4().hex
        self.observer_kind = observer_kind.strip()
        self.process_id = os.getpid()
        self._closed = False
        atexit.register(self.disconnect)
        self.heartbeat()

    def heartbeat(self) -> None:
        """Mark the observer as connected without affecting the agent run."""

        if self._closed:
            return
        self._publish(ConnectionStatus.CONNECTED)

    def disconnect(self) -> None:
        """Mark this registration disconnected if it still owns the file."""

        if self._closed:
            return
        self._closed = True
        try:
            current = read_connection_state(self.path)
            if current.connection_id != self.connection_id:
                return
            write_connection_state(
                self._state(ConnectionStatus.DISCONNECTED),
                self.path,
            )
        except Exception:
            # Connection reporting is auxiliary and must never change agent
            # behavior during shutdown.
            return

    def _publish(self, status: ConnectionStatus) -> None:
        try:
            write_connection_state(self._state(status), self.path)
        except Exception:
            # The observer remains usable when the local status file cannot be
            # written (for example, a read-only trace directory).
            return

    def _state(self, status: ConnectionStatus) -> ConnectionState:
        return ConnectionState(
            status=status,
            updated_at=datetime.now(UTC),
            connection_id=self.connection_id,
            observer_kind=self.observer_kind,
            process_id=self.process_id,
        )


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(value) > 128:
        raise ValueError(f"{field_name} is too long")
    return value


__all__ = [
    "CONNECTION_STATE_FILENAME",
    "CONNECTION_STATE_SCHEMA_VERSION",
    "ConnectionReporter",
    "ConnectionState",
    "ConnectionStatus",
    "connection_state_from_dict",
    "connection_state_to_dict",
    "read_connection_state",
    "write_connection_state",
]
