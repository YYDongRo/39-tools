from datetime import UTC, datetime

import pytest

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.integrations.playwright import (
    TextExpectation,
    diagnose_playwright_click_failure,
    record_playwright_click,
)


class FakeLocator:
    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        return self._count


class FakePage:
    def __init__(self, locator: FakeLocator) -> None:
        self._locator = locator

    def locator(self, selector: str) -> FakeLocator:
        return self._locator


class FailingLocator:
    def count(self) -> int:
        raise RuntimeError("page was closed")


def make_failed_click() -> ActionRecord:
    return ActionRecord(
        action_type="click",
        arguments={"selector": ".target"},
        start_time=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
        duration_ms=100,
        status=ActionStatus.FAILURE,
        failure_reason="TimeoutError: click timed out",
        failure_category=FailureCategory.TIMEOUT,
    )


@pytest.mark.parametrize("selector", ["", "   ", None])
def test_record_playwright_click_rejects_invalid_selector(
    selector: object,
) -> None:
    with pytest.raises(ValueError, match="selector cannot be empty"):
        record_playwright_click(object(), selector)  # type: ignore[arg-type]


@pytest.mark.parametrize("timeout_ms", [0, -1, True])
def test_record_playwright_click_rejects_invalid_timeout(
    timeout_ms: object,
) -> None:
    with pytest.raises(ValueError, match="timeout_ms must be a positive integer"):
        record_playwright_click(
            object(),
            "#target",
            timeout_ms=timeout_ms,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("selector", ["", "   ", None])
def test_text_expectation_rejects_invalid_selector(selector: object) -> None:
    with pytest.raises(ValueError, match="selector cannot be empty"):
        TextExpectation(selector=selector, expected="Saved")  # type: ignore[arg-type]


def test_text_expectation_rejects_non_string_expected_value() -> None:
    with pytest.raises(ValueError, match="expected must be a string"):
        TextExpectation(selector="#status", expected=True)  # type: ignore[arg-type]


@pytest.mark.parametrize("timeout_ms", [0, -1, True])
def test_text_expectation_rejects_invalid_timeout(timeout_ms: object) -> None:
    with pytest.raises(ValueError, match="timeout_ms must be a positive integer"):
        TextExpectation(
            selector="#status",
            expected="Saved",
            timeout_ms=timeout_ms,  # type: ignore[arg-type]
        )


def test_ambiguous_selector_preserves_original_category() -> None:
    action = diagnose_playwright_click_failure(
        FakePage(FakeLocator(count=2)),  # type: ignore[arg-type]
        make_failed_click(),
    )

    assert action.failure_category is FailureCategory.TIMEOUT
    assert action.failure_evidence == {
        "selector": ".target",
        "selector_count": 2,
        "target_visible": None,
        "target_enabled": None,
    }


def test_diagnostic_error_preserves_original_category() -> None:
    action = diagnose_playwright_click_failure(
        FakePage(FailingLocator()),  # type: ignore[arg-type]
        make_failed_click(),
    )

    assert action.failure_category is FailureCategory.TIMEOUT
    assert action.failure_evidence["diagnostic_error_type"] == "RuntimeError"
