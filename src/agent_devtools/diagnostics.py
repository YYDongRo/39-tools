"""Small, safe classifications for runs that stop before final verification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from agent_devtools.session import ActionSession


class RunIssueCode(StrEnum):
    """Machine-readable reasons a provider-backed run could not finish."""

    PROVIDER_CREDENTIALS = "provider_credentials"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class RunIssue:
    """A concise, actionable explanation for an unverified provider run."""

    code: RunIssueCode
    title: str
    detail: str
    next_step: str


def classify_run_issue(session: ActionSession) -> RunIssue | None:
    """Classify known Browser Use provider interruptions without raw errors.

    The adapter already stores a sanitized verification note. This function
    only interprets the stable messages produced by that adapter and leaves
    unrelated verification notes untouched.
    """

    if session.verification is not None:
        return None
    note = session.verification_note
    if session.verification_source != "browser-use" or note is None:
        return None

    normalized = note.casefold()
    if "rejected its credentials" in normalized or "api key" in normalized:
        return RunIssue(
            code=RunIssueCode.PROVIDER_CREDENTIALS,
            title="Provider credentials rejected",
            detail=(
                "The model provider rejected its credentials before final "
                "task verification."
            ),
            next_step="Check the provider key and selected model, then retry.",
        )
    if "rate-limited" in normalized or "rate limit" in normalized:
        return RunIssue(
            code=RunIssueCode.PROVIDER_RATE_LIMITED,
            title="Provider rate limit reached",
            detail=(
                "The model provider stopped the run before final task "
                "verification."
            ),
            next_step="Wait for quota recovery, then retry the task.",
        )
    if "provider timeout" in normalized:
        return RunIssue(
            code=RunIssueCode.PROVIDER_TIMEOUT,
            title="Provider timed out",
            detail=(
                "The model provider timed out before final task "
                "verification."
            ),
            next_step="Check provider latency or retry the task later.",
        )
    if "model provider" in normalized:
        return RunIssue(
            code=RunIssueCode.PROVIDER_ERROR,
            title="Provider stopped the run",
            detail=(
                "The model provider did not return a usable final task "
                "verification."
            ),
            next_step="Check the provider logs and retry the task.",
        )
    return None


__all__ = ["RunIssue", "RunIssueCode", "classify_run_issue"]
