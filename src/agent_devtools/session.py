from dataclasses import dataclass, field

from agent_devtools.action import ActionOutcome, ActionRecord


@dataclass
class ActionSession:
    actions: list[ActionRecord] = field(default_factory=list)

    @property
    def action_count(self) -> int:
        return len(self.actions)

    @property
    def has_failures(self) -> bool:
        return any(
            action.outcome is ActionOutcome.FAILURE for action in self.actions
        )
