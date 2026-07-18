import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.serialization import (
    read_session_json,
    session_from_dict,
    session_to_dict,
    write_session_json,
)
from agent_devtools.session import ActionSession


def make_action(
    status: ActionStatus,
    failure_reason: str | None = None,
) -> ActionRecord:
    return ActionRecord(
        action_type="click",
        arguments={"selector": "#agent-action"},
        start_time=datetime(2026, 7, 18, 7, 0, tzinfo=UTC),
        duration_ms=125,
        status=status,
        failure_reason=failure_reason,
    )


def test_session_summarizes_actions() -> None:
    session = ActionSession(
        actions=[
            make_action(ActionStatus.SUCCESS),
            make_action(ActionStatus.FAILURE, "target was not found"),
        ]
    )

    assert session.action_count == 2
    assert session.has_failures


def test_empty_session_has_no_failures() -> None:
    session = ActionSession()

    assert session.action_count == 0
    assert not session.has_failures


def test_session_json_round_trip(tmp_path: Path) -> None:
    session = ActionSession(
        actions=[
            make_action(ActionStatus.SUCCESS),
            make_action(ActionStatus.FAILURE, "target was not found"),
        ]
    )
    output_path = tmp_path / "session.json"

    write_session_json(session, output_path)

    loaded_session = read_session_json(output_path)
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert loaded_session == session
    assert data["schema_version"] == 1
    assert len(data["actions"]) == 2


def test_reject_unsupported_session_schema_version() -> None:
    data = session_to_dict(ActionSession())
    data["schema_version"] = 2

    with pytest.raises(ValueError, match="unsupported session schema_version: 2"):
        session_from_dict(data)
