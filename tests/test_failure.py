from agent_devtools.failure import FailureCategory, classify_exception


def test_classify_timeout_exception() -> None:
    assert classify_exception(TimeoutError("operation timed out")) is (
        FailureCategory.TIMEOUT
    )


def test_classify_other_exception_as_operation_error() -> None:
    assert classify_exception(RuntimeError("operation failed")) is (
        FailureCategory.OPERATION_ERROR
    )
