from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.recorder import record_action
from agent_devtools.report import write_action_html
from agent_devtools.serialization import write_action_json
from agent_devtools.session_recorder import SessionRecorder
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


@dataclass(frozen=True)
class VisibilityExpectation:
    selector: str
    timeout_ms: int = 2_000

    def __post_init__(self) -> None:
        if not isinstance(self.selector, str) or not self.selector.strip():
            raise ValueError("selector cannot be empty")
        if (
            not isinstance(self.timeout_ms, int)
            or isinstance(self.timeout_ms, bool)
            or self.timeout_ms <= 0
        ):
            raise ValueError("timeout_ms must be a positive integer")


@dataclass(frozen=True)
class InputValueExpectation:
    timeout_ms: int = 2_000

    def __post_init__(self) -> None:
        if (
            not isinstance(self.timeout_ms, int)
            or isinstance(self.timeout_ms, bool)
            or self.timeout_ms <= 0
        ):
            raise ValueError("timeout_ms must be a positive integer")


@dataclass(frozen=True)
class PlaywrightAction:
    action_type: str
    arguments: dict[str, object]
    expectation: (
        TextExpectation
        | VisibilityExpectation
        | InputValueExpectation
        | None
    ) = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.action_type, str)
            or not self.action_type.strip()
        ):
            raise ValueError("action_type cannot be empty")
        if not isinstance(self.arguments, dict) or not all(
            isinstance(key, str) for key in self.arguments
        ):
            raise ValueError("arguments must be a dictionary with string keys")
        if self.expectation is not None and not isinstance(
            self.expectation,
            (TextExpectation, VisibilityExpectation, InputValueExpectation),
        ):
            raise ValueError(
                "expectation must be a TextExpectation, "
                "VisibilityExpectation, InputValueExpectation, or None"
            )
        if (
            isinstance(self.expectation, InputValueExpectation)
            and self.action_type != "fill"
        ):
            raise ValueError(
                "InputValueExpectation can only verify fill actions"
            )


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

        evidence: dict[str, object] = {
            "expectation_type": "text_equals",
            "selector": expectation.selector,
            "selector_count": selector_count,
            "timeout_ms": expectation.timeout_ms,
        }
        if selector_count != 1:
            return VerificationResult(
                expected_state=expectation.expected,
                observed_state=observed,
                passed=False,
                evidence=evidence,
                failure_reason=(
                    f"expected selector {expectation.selector!r} to match "
                    f"exactly one element, observed {selector_count}"
                ),
            )

        return verify_text_state(
            expected_state=expectation.expected,
            observed_state=observed,
            evidence=evidence,
        )

    return verify


def expect_visible(
    page: Page,
    expectation: VisibilityExpectation,
) -> Callable[[], VerificationResult]:
    def verify() -> VerificationResult:
        from playwright.sync_api import expect

        locator = page.locator(expectation.selector)
        try:
            expect(locator).to_have_count(1, timeout=expectation.timeout_ms)
            expect(locator).to_be_visible(timeout=expectation.timeout_ms)
        except AssertionError:
            selector_count = locator.count()
            target_visible = (
                locator.first.is_visible() if selector_count == 1 else None
            )
        else:
            selector_count = 1
            target_visible = True

        expected_state = f"{expectation.selector!r} is visible"
        evidence: dict[str, object] = {
            "expectation_type": "element_visible",
            "selector": expectation.selector,
            "selector_count": selector_count,
            "target_visible": target_visible,
            "timeout_ms": expectation.timeout_ms,
            "url": page.url,
        }
        if selector_count != 1:
            return VerificationResult(
                expected_state=expected_state,
                observed_state=f"{selector_count} matching elements",
                passed=False,
                evidence=evidence,
                failure_reason=(
                    f"expected selector {expectation.selector!r} to match "
                    f"exactly one element, observed {selector_count}"
                ),
            )
        if not target_visible:
            return VerificationResult(
                expected_state=expected_state,
                observed_state=f"{expectation.selector!r} is hidden",
                passed=False,
                evidence=evidence,
                failure_reason=(
                    f"expected selector {expectation.selector!r} to be visible"
                ),
            )

        return VerificationResult(
            expected_state=expected_state,
            observed_state=expected_state,
            passed=True,
            evidence=evidence,
        )

    return verify


def expect_input_value(
    page: Page,
    selector: str,
    expected: str,
    expectation: InputValueExpectation,
) -> Callable[[], VerificationResult]:
    def verify() -> VerificationResult:
        from playwright.sync_api import expect

        locator = page.locator(selector)
        try:
            expect(locator).to_have_count(1, timeout=expectation.timeout_ms)
            expect(locator).to_have_value(
                expected,
                timeout=expectation.timeout_ms,
            )
        except AssertionError:
            selector_count = locator.count()
            observed = (
                locator.first.input_value()
                if selector_count > 0
                else "<element not found>"
            )
        else:
            selector_count = 1
            observed = locator.input_value()

        evidence: dict[str, object] = {
            "expectation_type": "input_value_equals",
            "selector": selector,
            "selector_count": selector_count,
            "timeout_ms": expectation.timeout_ms,
        }
        if selector_count != 1:
            return VerificationResult(
                expected_state=expected,
                observed_state=observed,
                passed=False,
                evidence=evidence,
                failure_reason=(
                    f"expected selector {selector!r} to match exactly one "
                    f"element, observed {selector_count}"
                ),
            )

        return verify_text_state(
            expected_state=expected,
            observed_state=observed,
            evidence=evidence,
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


def record_playwright_click_trace(
    page: Page,
    selector: str,
    output_dir: Path,
    *,
    timeout_ms: int | None = None,
    verification: Callable[[], VerificationResult] | None = None,
) -> ActionRecord:
    if output_dir.exists() and (
        not output_dir.is_dir() or any(output_dir.iterdir())
    ):
        raise FileExistsError(
            f"trace output directory is not empty: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    before_path = output_dir / "before.png"
    after_path = output_dir / "after.png"
    action_path = output_dir / "action.json"
    report_path = output_dir / "report.html"

    page.screenshot(path=str(before_path), full_page=True)
    action = record_playwright_click(
        page,
        selector,
        timeout_ms=timeout_ms,
        screenshot_before=Path("before.png"),
        screenshot_after=Path("after.png"),
        verification=verification,
    )

    try:
        page.screenshot(path=str(after_path), full_page=True)
    except Exception:
        action.screenshot_after = None
        write_action_json(action, action_path)
        write_action_html(action, report_path)
        raise

    write_action_json(action, action_path)
    write_action_html(action, report_path)
    return action


def record_playwright_action(
    page: Page,
    recorder: SessionRecorder,
    action_type: str,
    arguments: dict[str, object],
    *,
    verification: Callable[[], VerificationResult] | None = None,
) -> ActionRecord:
    observations: dict[str, object] = {}
    timeout_ms = arguments.get("timeout_ms")
    if timeout_ms is not None and (
        not isinstance(timeout_ms, int)
        or isinstance(timeout_ms, bool)
        or timeout_ms <= 0
    ):
        raise ValueError("timeout_ms must be a positive integer")

    if action_type == "navigate":
        url = arguments.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("navigate actions require a non-empty URL")
        if timeout_ms is None:
            operation = lambda: page.goto(url)
        else:
            operation = lambda: page.goto(url, timeout=timeout_ms)
    elif action_type in {"click", "fill"}:
        selector = arguments.get("selector")
        if not isinstance(selector, str) or not selector.strip():
            raise ValueError(
                "click and fill actions require a non-empty selector"
            )
        locator = page.locator(selector)
        if action_type == "click":
            if timeout_ms is None:
                operation = locator.click
            else:
                operation = lambda: locator.click(timeout=timeout_ms)
        else:
            text = arguments.get("text")
            if not isinstance(text, str):
                raise ValueError("fill actions require text")

            def execute_fill() -> None:
                try:
                    if timeout_ms is None:
                        locator.fill(text)
                    else:
                        locator.fill(text, timeout=timeout_ms)
                finally:
                    try:
                        selector_count = locator.count()
                        if selector_count == 1:
                            observations["input_value_after"] = (
                                locator.input_value(timeout=100)
                            )
                        else:
                            observations["input_value_after"] = None
                            observations["selector_count_after"] = (
                                selector_count
                            )
                    except Exception as error:
                        observations["input_value_error_type"] = type(
                            error
                        ).__name__

            operation = execute_fill
    else:
        raise ValueError(f"unsupported Playwright action: {action_type}")

    return recorder.record(
        action_type,
        dict(arguments),
        operation,
        observations=observations,
        verification=verification,
    )


def run_playwright_agent(
    page: Page,
    recorder: SessionRecorder,
    decide_next_action: Callable[[Page], PlaywrightAction | None],
    *,
    max_steps: int = 100,
) -> list[ActionRecord]:
    if (
        not isinstance(max_steps, int)
        or isinstance(max_steps, bool)
        or max_steps <= 0
    ):
        raise ValueError("max_steps must be a positive integer")

    recorded_actions: list[ActionRecord] = []
    for _ in range(max_steps):
        next_action = decide_next_action(page)
        if next_action is None:
            return recorded_actions
        if not isinstance(next_action, PlaywrightAction):
            raise TypeError(
                "decide_next_action must return a PlaywrightAction or None"
            )

        if isinstance(next_action.expectation, TextExpectation):
            verification = expect_text(page, next_action.expectation)
        elif isinstance(next_action.expectation, VisibilityExpectation):
            verification = expect_visible(page, next_action.expectation)
        elif isinstance(next_action.expectation, InputValueExpectation):
            selector = next_action.arguments.get("selector")
            text = next_action.arguments.get("text")
            if not isinstance(selector, str) or not selector.strip():
                raise ValueError(
                    "fill actions require a non-empty selector"
                )
            if not isinstance(text, str):
                raise ValueError("fill actions require text")
            verification = expect_input_value(
                page,
                selector,
                text,
                next_action.expectation,
            )
        else:
            verification = None

        action = record_playwright_action(
            page,
            recorder,
            next_action.action_type,
            next_action.arguments,
            verification=verification,
        )
        recorded_actions.append(action)
        if action.status is ActionStatus.FAILURE:
            return recorded_actions

    raise RuntimeError(f"agent did not finish within {max_steps} steps")


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
