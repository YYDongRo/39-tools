import pytest

from agent_devtools.verification import VerificationResult, verify_text_state


def test_matching_text_state_passes() -> None:
    result = verify_text_state(
        expected_state="Action complete",
        observed_state="Action complete",
        evidence={"selector": "#status"},
    )

    assert result.passed
    assert result.expected_state == "Action complete"
    assert result.observed_state == "Action complete"
    assert result.evidence == {"selector": "#status"}
    assert result.failure_reason is None


def test_mismatched_text_state_fails_with_reason() -> None:
    result = verify_text_state(
        expected_state="Action complete",
        observed_state="Waiting for the agent.",
    )

    assert not result.passed
    assert result.failure_reason == (
        "expected 'Action complete', observed 'Waiting for the agent.'"
    )


def test_failed_verification_requires_reason() -> None:
    with pytest.raises(
        ValueError,
        match="failed verifications require a failure reason",
    ):
        VerificationResult(
            expected_state="Action complete",
            observed_state="Waiting for the agent.",
            passed=False,
        )


def test_passed_verification_rejects_failure_reason() -> None:
    with pytest.raises(
        ValueError,
        match="passed verifications cannot have a failure reason",
    ):
        VerificationResult(
            expected_state="Action complete",
            observed_state="Action complete",
            passed=True,
            failure_reason="states did not match",
        )
