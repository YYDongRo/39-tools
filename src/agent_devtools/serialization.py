import json
from datetime import UTC, datetime
from pathlib import Path

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.session import ActionSession


SCHEMA_VERSION = 1
SESSION_SCHEMA_VERSION = 1


def action_to_dict(action: ActionRecord) -> dict[str, object]:
    if action.start_time.utcoffset() is None:
        raise ValueError("start_time must be timezone-aware")

    return {
        "schema_version": SCHEMA_VERSION,
        "action_type": action.action_type,
        "arguments": action.arguments,
        "start_time": action.start_time.astimezone(UTC).isoformat(),
        "duration_ms": action.duration_ms,
        "status": action.status.value,
        "screenshot_before": (
            action.screenshot_before.as_posix()
            if action.screenshot_before is not None
            else None
        ),
        "screenshot_after": (
            action.screenshot_after.as_posix()
            if action.screenshot_after is not None
            else None
        ),
        "failure_reason": action.failure_reason,
    }


def action_from_dict(data: dict[str, object]) -> ActionRecord:
    schema_version = data.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {schema_version!r}")

    try:
        action_type = data["action_type"]
        arguments = data["arguments"]
        start_time_value = data["start_time"]
        duration_ms = data["duration_ms"]
        status_value = data["status"]
        screenshot_before = data["screenshot_before"]
        screenshot_after = data["screenshot_after"]
        failure_reason = data["failure_reason"]
    except KeyError as error:
        raise ValueError(f"missing required field: {error.args[0]}") from error

    if not isinstance(action_type, str):
        raise ValueError("action_type must be a string")
    if not isinstance(arguments, dict) or not all(
        isinstance(key, str) for key in arguments
    ):
        raise ValueError("arguments must be an object with string keys")
    if not isinstance(start_time_value, str):
        raise ValueError("start_time must be a string")
    if not isinstance(duration_ms, int) or isinstance(duration_ms, bool):
        raise ValueError("duration_ms must be an integer")
    if not isinstance(status_value, str):
        raise ValueError("status must be a string")
    if screenshot_before is not None and not isinstance(screenshot_before, str):
        raise ValueError("screenshot_before must be a string or null")
    if screenshot_after is not None and not isinstance(screenshot_after, str):
        raise ValueError("screenshot_after must be a string or null")
    if failure_reason is not None and not isinstance(failure_reason, str):
        raise ValueError("failure_reason must be a string or null")

    try:
        start_time = datetime.fromisoformat(start_time_value)
    except ValueError as error:
        raise ValueError("start_time must be a valid ISO 8601 timestamp") from error
    if start_time.utcoffset() is None:
        raise ValueError("start_time must be timezone-aware")

    try:
        status = ActionStatus(status_value)
    except ValueError as error:
        raise ValueError(f"invalid status: {status_value!r}") from error

    return ActionRecord(
        action_type=action_type,
        arguments=dict(arguments),
        start_time=start_time.astimezone(UTC),
        duration_ms=duration_ms,
        status=status,
        screenshot_before=(
            Path(screenshot_before) if screenshot_before is not None else None
        ),
        screenshot_after=(
            Path(screenshot_after) if screenshot_after is not None else None
        ),
        failure_reason=failure_reason,
    )


def write_action_json(action: ActionRecord, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(action_to_dict(action), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_action_json(input_path: Path) -> ActionRecord:
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid action JSON: {error.msg}") from error

    if not isinstance(data, dict):
        raise ValueError("action JSON must contain an object")

    return action_from_dict(data)


def session_to_dict(session: ActionSession) -> dict[str, object]:
    return {
        "schema_version": SESSION_SCHEMA_VERSION,
        "actions": [action_to_dict(action) for action in session.actions],
    }


def session_from_dict(data: dict[str, object]) -> ActionSession:
    schema_version = data.get("schema_version")
    if schema_version != SESSION_SCHEMA_VERSION:
        raise ValueError(f"unsupported session schema_version: {schema_version!r}")

    try:
        actions_value = data["actions"]
    except KeyError as error:
        raise ValueError("missing required field: actions") from error
    if not isinstance(actions_value, list):
        raise ValueError("actions must be an array")

    actions: list[ActionRecord] = []
    for index, action_value in enumerate(actions_value):
        if not isinstance(action_value, dict):
            raise ValueError(f"action at index {index} must be an object")
        try:
            actions.append(action_from_dict(action_value))
        except ValueError as error:
            raise ValueError(f"invalid action at index {index}: {error}") from error

    return ActionSession(actions=actions)


def write_session_json(session: ActionSession, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(session_to_dict(session), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_session_json(input_path: Path) -> ActionSession:
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid session JSON: {error.msg}") from error

    if not isinstance(data, dict):
        raise ValueError("session JSON must contain an object")

    return session_from_dict(data)
