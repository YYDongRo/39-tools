from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path


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

    def __post_init__(self) -> None:
        if self.duration_ms < 0:
            raise ValueError("duration_ms cannot be negative")
        if self.status is ActionStatus.FAILURE and not self.failure_reason:
            raise ValueError("failed actions require a failure reason")
