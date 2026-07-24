from enum import StrEnum


class FailureCategory(StrEnum):
    TIMEOUT = "timeout"
    OPERATION_ERROR = "operation_error"
    VERIFICATION_MISMATCH = "verification_mismatch"
    TARGET_NOT_FOUND = "target_not_found"
    TARGET_AMBIGUOUS = "target_ambiguous"
    TARGET_NOT_VISIBLE = "target_not_visible"
    TARGET_DISABLED = "target_disabled"
    UNKNOWN = "unknown"


def classify_exception(error: Exception) -> FailureCategory:
    if any(base.__name__ == "TimeoutError" for base in type(error).__mro__):
        return FailureCategory.TIMEOUT
    return FailureCategory.OPERATION_ERROR
