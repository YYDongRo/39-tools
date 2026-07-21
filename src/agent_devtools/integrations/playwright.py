from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.recorder import record_action
from agent_devtools.verification import VerificationResult, verify_text_state


if TYPE_CHECKING:
    from playwright.sync_api import Page


@dataclass(frozen=True)
class TextExpectation:
    selector: str
    expected: str
    timeout_ms: int = 2_000

    def __post_init__(self) -> None:
        if not isinstance(self.selector, str) or not self.selector.strip():
            raise ValueError("selector cannot be empty")
        if not isinstance(self.expected, str):
            raise ValueError("expected must be a string")
        if (
            not isinstance(self.timeout_ms, int)
            or isinstance(self.timeout_ms, bool)
            or self.timeout_ms <= 0
        ):
            raise ValueError("timeout_ms must be a positive integer")


def expect_text(
    page: Page,
    expectation: TextExpectation,
) -> Callable[[], VerificationResult]:
    def verify() -> VerificationResult:
        from playwright.sync_api import expect

        locator = page.locator(expectation.selector)
        try:
            expect(locator).to_have_count(1, timeout=expectation.timeout_ms)
            expect(locator).to_have_text(
                expectation.expected,
                timeout=expectation.timeout_ms,
                use_inner_text=True,
            )
        except AssertionError:
            selector_count = locator.count()
            observed = (
                locator.first.inner_text()
                if selector_count > 0
                else "<element not found>"
            )
        else:
            selector_count = 1
            observed = locator.inner_text()

        return verify_text_state(
            expected_state=expectation.expected,
            observed_state=observed,
            evidence={
                "expectation_type": "text_equals",
                "selector": expectation.selector,
                "selector_count": selector_count,
                "timeout_ms": expectation.timeout_ms,
            },
        )

    return verify


def record_playwright_click(
    page: Page,
    selector: str,
    *,
    timeout_ms: int | None = None,
    screenshot_before: Path | None = None,
    screenshot_after: Path | None = None,
    verification: Callable[[], VerificationResult] | None = None,
) -> ActionRecord:
    if not isinstance(selector, str) or not selector.strip():
        raise ValueError("selector cannot be empty")
    if timeout_ms is not None and (
        not isinstance(timeout_ms, int)
        or isinstance(timeout_ms, bool)
        or timeout_ms <= 0
    ):
        raise ValueError("timeout_ms must be a positive integer")

    arguments: dict[str, object] = {"selector": selector}
    if timeout_ms is not None:
        arguments["timeout_ms"] = timeout_ms

    def execute_click() -> None:
        if timeout_ms is None:
            page.locator(selector).click()
        else:
            page.locator(selector).click(timeout=timeout_ms)

    action = record_action(
        action_type="click",
        arguments=arguments,
        operation=execute_click,
        screenshot_before=screenshot_before,
        screenshot_after=screenshot_after,
        verification=verification,
    )
    if action.status is ActionStatus.FAILURE:
        return diagnose_playwright_click_failure(page, action)
    return action


def diagnose_playwright_click_failure(
    page: Page,
    action: ActionRecord,
) -> ActionRecord:
    if action.action_type != "click" or action.status is not ActionStatus.FAILURE:
        raise ValueError("only failed click actions can be diagnosed")

    selector = action.arguments.get("selector")
    if not isinstance(selector, str) or not selector.strip():
        raise ValueError("failed click actions require a non-empty selector")

    evidence: dict[str, object] = {
        "selector": selector,
        "selector_count": None,
        "target_visible": None,
        "target_enabled": None,
    }
    category = action.failure_category

    try:
        locator = page.locator(selector)
        selector_count = locator.count()
        evidence["selector_count"] = selector_count

        if selector_count == 0:
            category = FailureCategory.TARGET_NOT_FOUND
        elif selector_count == 1:
            target = locator.first
            target_visible = target.is_visible()
            target_enabled = target.is_enabled()
            evidence["target_visible"] = target_visible
            evidence["target_enabled"] = target_enabled

            if not target_visible:
                category = FailureCategory.TARGET_NOT_VISIBLE
            elif not target_enabled:
                category = FailureCategory.TARGET_DISABLED
    except Exception as error:
        evidence["diagnostic_error_type"] = type(error).__name__

    return replace(
        action,
        failure_category=category,
        failure_evidence={**action.failure_evidence, **evidence},
    )
