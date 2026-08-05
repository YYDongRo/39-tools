"""Structured verification results for one agent trajectory."""

from __future__ import annotations

from dataclasses import dataclass

from agent_devtools.verification import VerificationResult


@dataclass(frozen=True)
class TrajectoryVerificationResult:
    """The final and action-level results returned by one trajectory judge.

    ``None`` means that the judge could not verify that item.  This keeps an
    unavailable model response separate from an explicit failed verification.
    """

    final: VerificationResult | None
    actions: tuple[VerificationResult | None, ...]
    source: str
    note: str | None = None
    action_notes: tuple[str | None, ...] = ()

    def __post_init__(self) -> None:
        if self.final is not None and not isinstance(
            self.final,
            VerificationResult,
        ):
            raise TypeError("final must be a VerificationResult or None")
        if not isinstance(self.actions, tuple):
            raise TypeError("actions must be a tuple")
        if not all(
            result is None or isinstance(result, VerificationResult)
            for result in self.actions
        ):
            raise TypeError(
                "actions must contain VerificationResult values or None"
            )
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source cannot be empty")
        if self.note is not None and (
            not isinstance(self.note, str) or not self.note.strip()
        ):
            raise ValueError("note cannot be empty")
        if not isinstance(self.action_notes, tuple):
            raise TypeError("action_notes must be a tuple")
        if len(self.action_notes) not in {0, len(self.actions)}:
            raise ValueError("action_notes must match the action count")
        if not all(
            note is None or isinstance(note, str) and note.strip()
            for note in self.action_notes
        ):
            raise ValueError("action notes must be non-empty strings or None")

    @property
    def action_count(self) -> int:
        return len(self.actions)


__all__ = ["TrajectoryVerificationResult"]
