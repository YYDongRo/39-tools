from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from agent_devtools.failure import FailureCategory
from agent_devtools.verification import VerificationResult


class ActionStatus(StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass
class ActionRecord:
    action_type: str
    arguments: dict[str, object]
    start_time: datetime
    duration_ms: int
    status: ActionStatus
    screenshot_before: Path | None = None
    screenshot_after: Path | None = None
    failure_reason: str | None = None
    failure_category: FailureCategory | None = None
    failure_evidence: dict[str, object] = field(default_factory=dict)
    verification: VerificationResult | None = None

    def __post_init__(self) -> None:
        if self.duration_ms < 0:
            raise ValueError("duration_ms cannot be negative")
        if self.status is ActionStatus.FAILURE and not self.failure_reason:
            raise ValueError("failed actions require a failure reason")
        if self.status is ActionStatus.FAILURE and self.failure_category is None:
            self.failure_category = FailureCategory.UNKNOWN
        if self.status is ActionStatus.SUCCESS and self.failure_category is not None:
            raise ValueError("successful actions cannot have a failure category")
        if self.status is ActionStatus.SUCCESS and self.failure_evidence:
            raise ValueError("successful actions cannot have failure evidence")
