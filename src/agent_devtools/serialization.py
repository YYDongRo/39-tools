import json
from datetime import UTC
from pathlib import Path

from agent_devtools.action import ActionRecord


SCHEMA_VERSION = 1


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


def write_action_json(action: ActionRecord, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(action_to_dict(action), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
