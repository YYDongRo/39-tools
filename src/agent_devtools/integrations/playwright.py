from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.recorder import record_action


if TYPE_CHECKING:
    from playwright.sync_api import Page


def record_playwright_click(
    page: Page,
    selector: str,
    *,
    timeout_ms: int | None = None,
    screenshot_before: Path | None = None,
    screenshot_after: Path | None = None,
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
