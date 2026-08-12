from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_devtools.connection import (
    CONNECTION_STATE_FILENAME,
    ConnectionReporter,
    ConnectionState,
    ConnectionStatus,
    connection_state_from_dict,
    connection_state_to_dict,
    read_connection_state,
    write_connection_state,
)


def test_connection_state_round_trips_with_safe_metadata(tmp_path: Path) -> None:
    state = ConnectionState(
        status=ConnectionStatus.CONNECTED,
        updated_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
        connection_id="connection-1",
        observer_kind="generic-agent",
        process_id=1234,
    )

    output = write_connection_state(
        state,
        tmp_path / CONNECTION_STATE_FILENAME,
    )

    assert read_connection_state(output) == state
    assert connection_state_from_dict(connection_state_to_dict(state)) == state
    assert "trace" not in output.read_text(encoding="utf-8")


def test_connection_reporter_marks_disconnect_only_for_its_registration(
    tmp_path: Path,
) -> None:
    reporter = ConnectionReporter(tmp_path, observer_kind="generic-agent")
    connected = read_connection_state(tmp_path / CONNECTION_STATE_FILENAME)

    assert connected.status is ConnectionStatus.CONNECTED
    assert connected.process_id is not None
    assert connected.observer_kind == "generic-agent"

    reporter.disconnect()
    disconnected = read_connection_state(
        tmp_path / CONNECTION_STATE_FILENAME,
    )
    assert disconnected.status is ConnectionStatus.DISCONNECTED
    assert disconnected.connection_id == connected.connection_id


def test_connection_state_rejects_invalid_timestamp_and_process_id() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ConnectionState(
            status=ConnectionStatus.CONNECTED,
            updated_at=datetime(2026, 8, 11, 12),
            connection_id="connection-1",
            observer_kind="generic-agent",
        )

    with pytest.raises(ValueError, match="positive"):
        ConnectionState(
            status=ConnectionStatus.CONNECTED,
            updated_at=datetime(2026, 8, 11, 12, tzinfo=UTC),
            connection_id="connection-1",
            observer_kind="generic-agent",
            process_id=0,
        )


def test_connection_state_from_dict_requires_versioned_fields() -> None:
    with pytest.raises(ValueError, match="schema"):
        connection_state_from_dict({"schema_version": 99})

    state = ConnectionState(
        status=ConnectionStatus.CONNECTED,
        updated_at=datetime.now(UTC) - timedelta(seconds=1),
        connection_id="connection-1",
        observer_kind="generic-agent",
    )
    data = connection_state_to_dict(state)
    del data["observer_kind"]
    with pytest.raises(ValueError, match="observer_kind"):
        connection_state_from_dict(data)
