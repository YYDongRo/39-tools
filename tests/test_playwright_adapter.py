from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.integrations.playwright import (
    InputValueExpectation,
    PlaywrightAction,
    TextExpectation,
    VisibilityExpectation,
    diagnose_playwright_click_failure,
    record_playwright_action,
    record_playwright_click,
    record_playwright_click_trace,
    run_playwright_agent,
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


@pytest.mark.parametrize("selector", ["", "   ", None])
def test_visibility_expectation_rejects_invalid_selector(
    selector: object,
) -> None:
    with pytest.raises(ValueError, match="selector cannot be empty"):
        VisibilityExpectation(selector=selector)  # type: ignore[arg-type]


@pytest.mark.parametrize("timeout_ms", [0, -1, True])
def test_visibility_expectation_rejects_invalid_timeout(
    timeout_ms: object,
) -> None:
    with pytest.raises(ValueError, match="timeout_ms must be a positive integer"):
        VisibilityExpectation(
            selector="#search",
            timeout_ms=timeout_ms,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("timeout_ms", [0, -1, True])
def test_input_value_expectation_rejects_invalid_timeout(
    timeout_ms: object,
) -> None:
    with pytest.raises(ValueError, match="timeout_ms must be a positive integer"):
        InputValueExpectation(
            timeout_ms=timeout_ms,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("action_type", ["", "   ", None])
def test_playwright_action_model_rejects_invalid_type(
    action_type: object,
) -> None:
    with pytest.raises(ValueError, match="action_type cannot be empty"):
        PlaywrightAction(action_type, {})  # type: ignore[arg-type]


def test_playwright_action_model_rejects_invalid_arguments() -> None:
    with pytest.raises(ValueError, match="arguments must be a dictionary"):
        PlaywrightAction("click", {1: "#target"})  # type: ignore[dict-item]


def test_playwright_action_model_rejects_invalid_expectation() -> None:
    with pytest.raises(ValueError, match="must be a TextExpectation"):
        PlaywrightAction(
            "navigate",
            {"url": "https://example.com"},
            expectation="visible",  # type: ignore[arg-type]
        )


def test_input_value_expectation_only_supports_fill_actions() -> None:
    with pytest.raises(ValueError, match="can only verify fill actions"):
        PlaywrightAction(
            "click",
            {"selector": "#search"},
            expectation=InputValueExpectation(),
        )


@pytest.mark.parametrize("max_steps", [0, -1, True])
def test_playwright_agent_rejects_invalid_max_steps(max_steps: object) -> None:
    with pytest.raises(ValueError, match="max_steps must be a positive integer"):
        run_playwright_agent(
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            lambda page: None,
            max_steps=max_steps,  # type: ignore[arg-type]
        )


def test_playwright_agent_rejects_invalid_decision() -> None:
    with pytest.raises(TypeError, match="must return a PlaywrightAction or None"):
        run_playwright_agent(
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            lambda page: "click",  # type: ignore[return-value]
        )


def test_playwright_agent_finishes_without_actions() -> None:
    actions = run_playwright_agent(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        lambda page: None,
    )

    assert actions == []


def test_click_trace_rejects_non_empty_output_directory(tmp_path: Path) -> None:
    (tmp_path / "existing.txt").write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="directory is not empty"):
        record_playwright_click_trace(
            object(),  # type: ignore[arg-type]
            "#target",
            tmp_path,
        )


@pytest.mark.parametrize("selector", ["", "   ", None])
def test_playwright_action_rejects_invalid_selector(selector: object) -> None:
    with pytest.raises(ValueError, match="require a non-empty selector"):
        record_playwright_action(
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            "click",
            {"selector": selector},
        )


@pytest.mark.parametrize("url", ["", "   ", None])
def test_playwright_navigate_action_rejects_invalid_url(url: object) -> None:
    with pytest.raises(ValueError, match="require a non-empty URL"):
        record_playwright_action(
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            "navigate",
            {"url": url},
        )


@pytest.mark.parametrize("timeout_ms", [0, -1, True])
def test_playwright_action_rejects_invalid_timeout(timeout_ms: object) -> None:
    with pytest.raises(ValueError, match="timeout_ms must be a positive integer"):
        record_playwright_action(
            FakePage(FakeLocator(count=1)),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            "click",
            {"selector": "#target", "timeout_ms": timeout_ms},
        )


def test_playwright_fill_action_requires_text() -> None:
    with pytest.raises(ValueError, match="fill actions require text"):
        record_playwright_action(
            FakePage(FakeLocator(count=1)),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            "fill",
            {"selector": "#target"},
        )


def test_playwright_action_rejects_unsupported_action_type() -> None:
    with pytest.raises(ValueError, match="unsupported Playwright action"):
        record_playwright_action(
            FakePage(FakeLocator(count=1)),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            "scroll",
            {"selector": "#target"},
        )


def test_diagnoses_ambiguous_selector() -> None:
    action = diagnose_playwright_click_failure(
        FakePage(FakeLocator(count=2)),  # type: ignore[arg-type]
        make_failed_click(),
    )

    assert action.failure_category is FailureCategory.TARGET_AMBIGUOUS
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
