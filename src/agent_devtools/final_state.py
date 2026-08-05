"""Framework-independent final-state evidence for agent verification."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agent_devtools.action import ActionRecord


@dataclass(frozen=True)
class FinalStateObservation:
    """Evidence passed to a generic agent's final-state verifier."""

    task: str
    state: dict[str, object]
    actions: tuple[ActionRecord, ...]
    screenshot_path: Path | None = None
    trace_directory: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.task, str) or not self.task.strip():
            raise ValueError("task must be a non-empty string")
        if not isinstance(self.state, dict) or not all(
            isinstance(key, str) for key in self.state
        ):
            raise TypeError("state must be a dictionary with string keys")
        try:
            normalized_state = json.loads(
                json.dumps(self.state, ensure_ascii=False, allow_nan=False)
            )
        except (TypeError, ValueError, RecursionError) as error:
            raise TypeError("state must contain JSON-safe values") from error
        if not isinstance(normalized_state, dict):
            raise TypeError("state must normalize to a dictionary")
        object.__setattr__(self, "state", normalized_state)

        actions = tuple(self.actions)
        if not all(isinstance(action, ActionRecord) for action in actions):
            raise TypeError("actions must contain ActionRecord values")
        object.__setattr__(self, "actions", actions)

        for field_name, value in (
            ("screenshot_path", self.screenshot_path),
            ("trace_directory", self.trace_directory),
        ):
            if value is not None and not isinstance(value, Path):
                raise TypeError(f"{field_name} must be a Path or None")

    @property
    def action_count(self) -> int:
        return len(self.actions)


__all__ = ["FinalStateObservation"]
