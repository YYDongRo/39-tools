from enum import StrEnum


class FailureCategory(StrEnum):
    TIMEOUT = "timeout"
    OPERATION_ERROR = "operation_error"
    VERIFICATION_MISMATCH = "verification_mismatch"
    UNKNOWN = "unknown"


def classify_exception(error: Exception) -> FailureCategory:
    if any(base.__name__ == "TimeoutError" for base in type(error).__mro__):
        return FailureCategory.TIMEOUT
    return FailureCategory.OPERATION_ERROR
