from dataclasses import dataclass, field

from agent_devtools.failure import FailureCategory


@dataclass
class VerificationResult:
    expected_state: str
    observed_state: str
    passed: bool
    evidence: dict[str, object] = field(default_factory=dict)
    failure_reason: str | None = None
    failure_category: FailureCategory | None = None

    def __post_init__(self) -> None:
        if self.passed and self.failure_reason is not None:
            raise ValueError("passed verifications cannot have a failure reason")
        if not self.passed and not self.failure_reason:
            raise ValueError("failed verifications require a failure reason")
        if not self.passed and self.failure_category is None:
            self.failure_category = FailureCategory.VERIFICATION_MISMATCH
        if self.passed and self.failure_category is not None:
            raise ValueError("passed verifications cannot have a failure category")


def verify_text_state(
    expected_state: str,
    observed_state: str,
    *,
    evidence: dict[str, object] | None = None,
) -> VerificationResult:
    passed = expected_state == observed_state
    failure_reason = None
    if not passed:
        failure_reason = f"expected {expected_state!r}, observed {observed_state!r}"

    return VerificationResult(
        expected_state=expected_state,
        observed_state=observed_state,
        passed=passed,
        evidence=dict(evidence) if evidence is not None else {},
        failure_reason=failure_reason,
        failure_category=(
            None if passed else FailureCategory.VERIFICATION_MISMATCH
        ),
    )
