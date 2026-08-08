from dataclasses import dataclass, field

from agent_devtools.action import ActionOutcome, ActionRecord
from agent_devtools.verification import VerificationResult


@dataclass
class ActionSession:
    actions: list[ActionRecord] = field(default_factory=list)
    goal: str | None = None
    inferred_goal: str | None = None
    verification_source: str | None = None
    verification_note: str | None = None
    # Optional machine-readable explanation for an unverified run.  It is
    # intentionally a string so the core session model does not depend on a
    # provider-specific diagnostics module.
    issue_code: str | None = None
    verification: VerificationResult | None = None
    auxiliary_events: list[dict[str, object]] = field(default_factory=list)

    def __post_init__(self) -> None:
        for index, event in enumerate(self.auxiliary_events):
            if not isinstance(event, dict) or not all(
                isinstance(key, str) for key in event
            ):
                raise TypeError(
                    "auxiliary event at index "
                    f"{index} must be an object with string keys"
                )
        _validate_optional_text(self.goal, "goal")
        _validate_optional_text(self.inferred_goal, "inferred_goal")
        _validate_optional_text(self.verification_source, "verification_source")
        _validate_optional_text(self.verification_note, "verification_note")
        _validate_optional_text(self.issue_code, "issue_code")
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


def _validate_optional_text(value: object, field_name: str) -> None:
    if value is not None and (
        not isinstance(value, str) or not value.strip()
    ):
        raise ValueError(f"{field_name} cannot be empty")
