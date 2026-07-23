import json
import os
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.session import ActionSession
from agent_devtools.verification import VerificationResult


SCHEMA_VERSION = 5
SUPPORTED_SCHEMA_VERSIONS = {1, 2, 3, 4, SCHEMA_VERSION}
SESSION_SCHEMA_VERSION = 2
SUPPORTED_SESSION_SCHEMA_VERSIONS = {1, SESSION_SCHEMA_VERSION}


def _write_json(data: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            )
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, output_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _verification_to_dict(
    verification: VerificationResult | None,
) -> dict[str, object] | None:
    if verification is None:
        return None

    return {
        "expected_state": verification.expected_state,
        "observed_state": verification.observed_state,
        "passed": verification.passed,
        "evidence": verification.evidence,
        "failure_reason": verification.failure_reason,
        "failure_category": (
            verification.failure_category.value
            if verification.failure_category is not None
            else None
        ),
    }


def _verification_from_dict(data: object) -> VerificationResult | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError("verification must be an object or null")

    try:
        expected_state = data["expected_state"]
        observed_state = data["observed_state"]
        passed = data["passed"]
        evidence = data["evidence"]
        failure_reason = data["failure_reason"]
        failure_category_value = data["failure_category"]
    except KeyError as error:
        raise ValueError(
            f"missing required verification field: {error.args[0]}"
        ) from error

    if not isinstance(expected_state, str):
        raise ValueError("verification expected_state must be a string")
    if not isinstance(observed_state, str):
        raise ValueError("verification observed_state must be a string")
    if not isinstance(passed, bool):
        raise ValueError("verification passed must be a boolean")
    if not isinstance(evidence, dict) or not all(
        isinstance(key, str) for key in evidence
    ):
        raise ValueError("verification evidence must be an object with string keys")
    if failure_reason is not None and not isinstance(failure_reason, str):
        raise ValueError("verification failure_reason must be a string or null")
    if failure_category_value is not None and not isinstance(
        failure_category_value, str
    ):
        raise ValueError("verification failure_category must be a string or null")

    try:
        failure_category = (
            FailureCategory(failure_category_value)
            if failure_category_value is not None
            else None
        )
    except ValueError as error:
        raise ValueError(
            f"invalid verification failure_category: {failure_category_value!r}"
        ) from error

    return VerificationResult(
        expected_state=expected_state,
        observed_state=observed_state,
        passed=passed,
        evidence=dict(evidence),
        failure_reason=failure_reason,
        failure_category=failure_category,
    )


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
        "failure_category": (
            action.failure_category.value
            if action.failure_category is not None
            else None
        ),
        "failure_evidence": action.failure_evidence,
        "observations": action.observations,
        "verification": _verification_to_dict(action.verification),
    }


def action_from_dict(data: dict[str, object]) -> ActionRecord:
    schema_version = data.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
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
        failure_category_value = (
            data["failure_category"]
            if schema_version in {2, 3, 4, SCHEMA_VERSION}
            else None
        )
        failure_evidence_value = (
            data["failure_evidence"]
            if schema_version in {3, 4, SCHEMA_VERSION}
            else {}
        )
        verification_value = (
            data["verification"]
            if schema_version in {4, SCHEMA_VERSION}
            else None
        )
        observations_value = (
            data["observations"] if schema_version == SCHEMA_VERSION else {}
        )
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
    if failure_category_value is not None and not isinstance(
        failure_category_value, str
    ):
        raise ValueError("failure_category must be a string or null")
    if not isinstance(failure_evidence_value, dict) or not all(
        isinstance(key, str) for key in failure_evidence_value
    ):
        raise ValueError("failure_evidence must be an object with string keys")
    if not isinstance(observations_value, dict) or not all(
        isinstance(key, str) for key in observations_value
    ):
        raise ValueError("observations must be an object with string keys")

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

    try:
        failure_category = (
            FailureCategory(failure_category_value)
            if failure_category_value is not None
            else None
        )
    except ValueError as error:
        raise ValueError(
            f"invalid failure_category: {failure_category_value!r}"
        ) from error

    verification = _verification_from_dict(verification_value)

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
        failure_category=failure_category,
        failure_evidence=dict(failure_evidence_value),
        observations=dict(observations_value),
        verification=verification,
    )


def write_action_json(action: ActionRecord, output_path: Path) -> None:
    _write_json(action_to_dict(action), output_path)


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
        "goal": session.goal,
        "verification": _verification_to_dict(session.verification),
        "actions": [action_to_dict(action) for action in session.actions],
    }


def session_from_dict(data: dict[str, object]) -> ActionSession:
    schema_version = data.get("schema_version")
    if schema_version not in SUPPORTED_SESSION_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported session schema_version: {schema_version!r}")

    try:
        actions_value = data["actions"]
        goal_value = (
            data["goal"] if schema_version == SESSION_SCHEMA_VERSION else None
        )
        verification_value = (
            data["verification"]
            if schema_version == SESSION_SCHEMA_VERSION
            else None
        )
    except KeyError as error:
        raise ValueError(f"missing required field: {error.args[0]}") from error
    if not isinstance(actions_value, list):
        raise ValueError("actions must be an array")
    if goal_value is not None and not isinstance(goal_value, str):
        raise ValueError("goal must be a string or null")

    actions: list[ActionRecord] = []
    for index, action_value in enumerate(actions_value):
        if not isinstance(action_value, dict):
            raise ValueError(f"action at index {index} must be an object")
        try:
            actions.append(action_from_dict(action_value))
        except ValueError as error:
            raise ValueError(f"invalid action at index {index}: {error}") from error

    verification = _verification_from_dict(verification_value)
    return ActionSession(
        actions=actions,
        goal=goal_value,
        verification=verification,
    )


def write_session_json(session: ActionSession, output_path: Path) -> None:
    _write_json(session_to_dict(session), output_path)


def read_session_json(input_path: Path) -> ActionSession:
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid session JSON: {error.msg}") from error

    if not isinstance(data, dict):
        raise ValueError("session JSON must contain an object")

    return session_from_dict(data)
