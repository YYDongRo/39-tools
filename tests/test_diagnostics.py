from agent_devtools.diagnostics import (
    RunIssueCode,
    classify_run_issue,
)
from agent_devtools.session import ActionSession


def test_classifies_browser_use_rate_limit_as_actionable_issue() -> None:
    session = ActionSession(
        goal="Open the requested page.",
        verification_source="browser-use",
        verification_note=(
            "Browser Use model provider rate-limited the run. "
            "Check provider quota and retry policy."
        ),
    )

    issue = classify_run_issue(session)

    assert issue is not None
    assert issue.code is RunIssueCode.PROVIDER_RATE_LIMITED
    assert issue.title == "Provider rate limit reached"
    assert "quota" in issue.next_step


def test_prefers_structured_issue_code_over_note_text() -> None:
    session = ActionSession(
        goal="Open the requested page.",
        verification_source="browser-use",
        issue_code=RunIssueCode.PROVIDER_RATE_LIMITED.value,
    )

    issue = classify_run_issue(session)

    assert issue is not None
    assert issue.code is RunIssueCode.PROVIDER_RATE_LIMITED


def test_classifies_browser_use_credentials_error_without_persisting_raw_text(
) -> None:
    session = ActionSession(
        goal="Open the requested page.",
        verification_source="browser-use",
        verification_note=(
            "Browser Use model provider rejected its credentials. "
            "Check provider setup and API key."
        ),
    )

    issue = classify_run_issue(session)

    assert issue is not None
    assert issue.code is RunIssueCode.PROVIDER_CREDENTIALS
    assert "API key" not in issue.detail


def test_does_not_classify_unrelated_or_verified_sessions() -> None:
    assert (
        classify_run_issue(
            ActionSession(
                goal="Open the requested page.",
                verification_source="gemini:final-state",
                verification_note="No reliable final state was available.",
            )
        )
        is None
    )
