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


_ISSUES = {
    RunIssueCode.PROVIDER_CREDENTIALS: RunIssue(
        code=RunIssueCode.PROVIDER_CREDENTIALS,
        title="Provider credentials rejected",
        detail=(
            "The model provider rejected its credentials before final "
            "task verification."
        ),
        next_step="Check the provider key and selected model, then retry.",
    ),
    RunIssueCode.PROVIDER_RATE_LIMITED: RunIssue(
        code=RunIssueCode.PROVIDER_RATE_LIMITED,
        title="Provider rate limit reached",
        detail=(
            "The model provider stopped the run before final task "
            "verification."
        ),
        next_step="Wait for quota recovery, then retry the task.",
    ),
    RunIssueCode.PROVIDER_TIMEOUT: RunIssue(
        code=RunIssueCode.PROVIDER_TIMEOUT,
        title="Provider timed out",
        detail=(
            "The model provider timed out before final task "
            "verification."
        ),
        next_step="Check provider latency or retry the task later.",
    ),
    RunIssueCode.PROVIDER_ERROR: RunIssue(
        code=RunIssueCode.PROVIDER_ERROR,
        title="Provider stopped the run",
        detail=(
            "The model provider did not return a usable final task "
            "verification."
        ),
        next_step="Check the provider logs and retry the task.",
    ),
}


def _issue_for_code(value: object) -> RunIssue | None:
    try:
        code = RunIssueCode(value)
    except (TypeError, ValueError):
        return None
    return _ISSUES.get(code)


def _issue_code_from_note(note: str) -> RunIssueCode | None:
    normalized = note.casefold()
    if "rejected its credentials" in normalized or "api key" in normalized:
        return RunIssueCode.PROVIDER_CREDENTIALS
    if "rate-limited" in normalized or "rate limit" in normalized:
        return RunIssueCode.PROVIDER_RATE_LIMITED
    if "provider timeout" in normalized:
        return RunIssueCode.PROVIDER_TIMEOUT
    if "model provider" in normalized:
        return RunIssueCode.PROVIDER_ERROR
    return None


def classify_run_issue(session: ActionSession) -> RunIssue | None:
    """Classify known Browser Use provider interruptions without raw errors.

    The adapter already stores a sanitized verification note. This function
    only interprets the stable messages produced by that adapter and leaves
    unrelated verification notes untouched.
    """

    if session.verification is not None:
        return None
    if session.verification_source != "browser-use":
        return None

    issue = _issue_for_code(session.issue_code)
    if issue is not None:
        return issue

    note = session.verification_note
    if note is None:
        return None
    return _issue_for_code(_issue_code_from_note(note))


__all__ = ["RunIssue", "RunIssueCode", "classify_run_issue"]
