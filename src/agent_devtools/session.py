from dataclasses import dataclass, field

from agent_devtools.action import ActionOutcome, ActionRecord
from agent_devtools.verification import VerificationResult


@dataclass
class ActionSession:
    actions: list[ActionRecord] = field(default_factory=list)
    goal: str | None = None
    verification: VerificationResult | None = None

    def __post_init__(self) -> None:
        if self.goal is not None and (
            not isinstance(self.goal, str) or not self.goal.strip()
        ):
            raise ValueError("goal cannot be empty")
        if self.verification is not None and not isinstance(
            self.verification, VerificationResult
        ):
            raise TypeError("verification must be a VerificationResult")
        if self.verification is not None and self.goal is None:
            raise ValueError("task verification requires a goal")

    @property
    def action_count(self) -> int:
        return len(self.actions)

    @property
    def has_failures(self) -> bool:
        task_failed = (
            self.verification is not None and not self.verification.passed
        )
        return task_failed or any(
            action.outcome is ActionOutcome.FAILURE for action in self.actions
        )

    @property
    def outcome(self) -> ActionOutcome:
        if self.verification is None:
            return ActionOutcome.UNVERIFIED
        if self.verification.passed:
            return ActionOutcome.SUCCESS
        return ActionOutcome.FAILURE
