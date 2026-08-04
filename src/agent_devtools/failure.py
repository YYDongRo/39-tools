from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_devtools.session import ActionSession


class FailureCategory(StrEnum):
    TIMEOUT = "timeout"
    OPERATION_ERROR = "operation_error"
    VERIFICATION_MISMATCH = "verification_mismatch"
    TARGET_NOT_FOUND = "target_not_found"
    TARGET_AMBIGUOUS = "target_ambiguous"
    TARGET_NOT_VISIBLE = "target_not_visible"
    TARGET_DISABLED = "target_disabled"
    TARGET_NOT_EDITABLE = "target_not_editable"
    UNKNOWN = "unknown"


def classify_exception(error: Exception) -> FailureCategory:
    if any(base.__name__ == "TimeoutError" for base in type(error).__mro__):
        return FailureCategory.TIMEOUT
    return FailureCategory.OPERATION_ERROR


def record_agent_run_failure(
    session: ActionSession,
    error: BaseException,
    *,
    runtime_name: str = "Agent",
) -> None:
    """Store a sanitized agent-run failure on an existing session."""

    session.verification = None
    session.verification_source = "agent-run"
    session.verification_note = (
        f"{runtime_name} run failed ({type(error).__name__})."
    )
