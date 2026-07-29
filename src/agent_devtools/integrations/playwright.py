from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Self, TypeVar

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.async_tool_recorder import (
    RecordedAsyncTools,
    record_async_tools,
)
from agent_devtools.failure import FailureCategory
from agent_devtools.integrations.playwright_events import (
    AsyncPlaywrightEventCollector,
    PlaywrightEventCollector,
)
from agent_devtools.integrations.playwright_task import (
    TaskExpectation,
    validate_task_expectation,
    verify_async_playwright_task,
    verify_playwright_task,
)
from agent_devtools.recorder import record_action
from agent_devtools.report import write_action_html
from agent_devtools.serialization import write_action_json
from agent_devtools.session import ActionSession
from agent_devtools.session_recorder import SessionRecorder
from agent_devtools.tool_recorder import RecordedTools, record_tools
from agent_devtools.verification import VerificationResult, verify_text_state


if TYPE_CHECKING:
    from playwright.async_api import Page as AsyncPage
    from playwright.sync_api import Page


PlaywrightToolT = TypeVar("PlaywrightToolT")


_PAGE_STATE_SCRIPT = """
() => {
  const root = document.documentElement;
  const active = document.activeElement;
  let focusedElement = null;

  if (
    active &&
    active !== document.body &&
    active !== document.documentElement
  ) {
    const bounds = active.getBoundingClientRect();
    focusedElement = {
      tag: active.tagName.toLowerCase(),
      id: active.id || null,
      role: active.getAttribute("role"),
      type: active.getAttribute("type"),
      editable: Boolean(
        active.isContentEditable ||
        ["INPUT", "SELECT", "TEXTAREA"].includes(active.tagName)
      ),
      bounds: {
        x: Math.round(bounds.x),
        y: Math.round(bounds.y),
        width: Math.round(bounds.width),
        height: Math.round(bounds.height),
      },
    };
  }

  return {
    url: window.location.href,
    title: document.title,
    ready_state: document.readyState,
    visibility_state: document.visibilityState,
    element_count: document.querySelectorAll("*").length,
    scroll: {
      x: Math.round(window.scrollX),
      y: Math.round(window.scrollY),
      max_x: root ? Math.max(0, root.scrollWidth - window.innerWidth) : 0,
      max_y: root ? Math.max(0, root.scrollHeight - window.innerHeight) : 0,
    },
    focused_element: focusedElement,
  };
}
"""


def observe_playwright_page(page: Page) -> dict[str, object]:
    state = page.evaluate(_PAGE_STATE_SCRIPT)
    return _normalize_page_state(state, page.viewport_size)


async def observe_async_playwright_page(
    page: AsyncPage,
) -> dict[str, object]:
    state = await page.evaluate(_PAGE_STATE_SCRIPT)
    return _normalize_page_state(state, page.viewport_size)


def _normalize_page_state(
    state: object,
    viewport_size: dict[str, int] | None,
) -> dict[str, object]:
    if not isinstance(state, dict):
        raise TypeError("Playwright page observation must be an object")

    return {
        "url": state.get("url"),
        "title": state.get("title"),
        "ready_state": state.get("ready_state"),
        "visibility_state": state.get("visibility_state"),
        "viewport": viewport_size,
        "scroll": state.get("scroll"),
        "focused_element": state.get("focused_element"),
        "element_count": state.get("element_count"),
    }


def record_playwright_tools(
    tools: PlaywrightToolT,
    page: Page,
    output_dir: str | Path,
    *,
    goal: str | None = None,
    task_verification: Callable[[], VerificationResult] | None = None,
    task_expectation: TaskExpectation | None = None,
    methods: Iterable[str] | None = None,
    full_page_screenshots: bool = False,
    capture_browser_events: bool = True,
    event_settle_ms: int = 100,
    max_browser_events: int = 20,
) -> RecordedTools[PlaywrightToolT]:
    if not isinstance(full_page_screenshots, bool):
        raise TypeError("full_page_screenshots must be a boolean")
    if not isinstance(capture_browser_events, bool):
        raise TypeError("capture_browser_events must be a boolean")
    if task_verification is not None and task_expectation is not None:
        raise ValueError(
            "use either task_verification or task_expectation, not both"
        )
    if task_expectation is not None:
        validate_task_expectation(task_expectation)
        task_verification = lambda: verify_playwright_task(
            page,
            task_expectation,
        )
    event_collector = None
    if capture_browser_events:
        event_collector = PlaywrightEventCollector(
            page,
            settle_ms=event_settle_ms,
            max_events=max_browser_events,
        )
    return record_tools(
        tools,
        output_dir,
        capture_screenshot=lambda path: page.screenshot(
            path=str(path),
            full_page=full_page_screenshots,
        ),
        observe_state=lambda: observe_playwright_page(page),
        goal=goal,
        task_verification=task_verification,
        methods=methods,
        event_collector=event_collector,
    )


def record_async_playwright_tools(
    tools: PlaywrightToolT,
    page: AsyncPage,
    output_dir: str | Path,
    *,
    goal: str | None = None,
    task_verification: (
        Callable[
            [],
            VerificationResult | Awaitable[VerificationResult],
        ]
        | None
    ) = None,
    task_expectation: TaskExpectation | None = None,
    methods: Iterable[str] | None = None,
    full_page_screenshots: bool = False,
    capture_browser_events: bool = True,
    event_settle_ms: int = 100,
    max_browser_events: int = 20,
) -> RecordedAsyncTools[PlaywrightToolT]:
    if not isinstance(full_page_screenshots, bool):
        raise TypeError("full_page_screenshots must be a boolean")
    if not isinstance(capture_browser_events, bool):
        raise TypeError("capture_browser_events must be a boolean")
    if task_verification is not None and task_expectation is not None:
        raise ValueError(
            "use either task_verification or task_expectation, not both"
        )
    if task_expectation is not None:
        validate_task_expectation(task_expectation)

        async def generated_task_verification() -> VerificationResult:
            return await verify_async_playwright_task(page, task_expectation)

        task_verification = generated_task_verification
    event_collector = None
    if capture_browser_events:
        event_collector = AsyncPlaywrightEventCollector(
            page,
            settle_ms=event_settle_ms,
            max_events=max_browser_events,
        )

    async def capture_screenshot(path: Path) -> None:
        await page.screenshot(
            path=str(path),
            full_page=full_page_screenshots,
        )

    async def observe_state() -> dict[str, object]:
        return await observe_async_playwright_page(page)

    return record_async_tools(
        tools,
        output_dir,
        capture_screenshot=capture_screenshot,
        observe_state=observe_state,
        goal=goal,
        task_verification=task_verification,
        methods=methods,
        event_collector=event_collector,
    )


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
    elif action_type in {"click", "fill", "press"}:
        selector = arguments.get("selector")
        if not isinstance(selector, str) or not selector.strip():
            raise ValueError(
                "click, fill, and press actions require a non-empty selector"
            )
        locator = page.locator(selector)
        if action_type == "click":
            if timeout_ms is None:
                operation = locator.click
            else:
                operation = lambda: locator.click(timeout=timeout_ms)
        elif action_type == "fill":
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
            key = arguments.get("key")
            if not isinstance(key, str) or not key.strip():
                raise ValueError("press actions require a non-empty key")
            if timeout_ms is None:
                operation = lambda: locator.press(key)
            else:
                operation = lambda: locator.press(key, timeout=timeout_ms)
    elif action_type == "scroll":
        if timeout_ms is not None:
            raise ValueError("scroll actions do not support timeout_ms")
        delta_x = _scroll_delta(arguments, "delta_x")
        delta_y = _scroll_delta(arguments, "delta_y")
        if delta_x == 0 and delta_y == 0:
            raise ValueError("scroll actions require a non-zero delta")

        def execute_scroll() -> None:
            page.mouse.wheel(delta_x, delta_y)
            page.wait_for_timeout(50)

        operation = execute_scroll
    else:
        raise ValueError(f"unsupported Playwright action: {action_type}")

    browser_operation = operation

    def execute_with_page_url_observations() -> None:
        _observe_page_url(page, observations, "page_url_before")
        if action_type == "scroll":
            _observe_scroll_position(page, observations, "scroll_before")
        try:
            browser_operation()
        finally:
            if action_type == "scroll":
                _observe_scroll_position(page, observations, "scroll_after")
            _observe_page_url(page, observations, "page_url_after")

    failure_diagnosis: Callable[[ActionRecord], ActionRecord] | None = None
    if action_type == "click":
        failure_diagnosis = lambda action: diagnose_playwright_click_failure(
            page,
            action,
        )
    elif action_type == "fill":
        failure_diagnosis = lambda action: diagnose_playwright_fill_failure(
            page,
            action,
        )
    elif action_type == "press":
        failure_diagnosis = lambda action: _diagnose_playwright_target_failure(
            page,
            action,
            str(action.arguments["selector"]),
            check_editable=False,
        )

    return recorder.record(
        action_type,
        dict(arguments),
        execute_with_page_url_observations,
        observations=observations,
        verification=verification,
        failure_diagnosis=failure_diagnosis,
    )


def _scroll_delta(arguments: dict[str, object], key: str) -> int | float:
    value = arguments.get(key, 0)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
    ):
        raise ValueError(
            "scroll actions require finite numeric delta_x and delta_y"
        )
    return value


def _observe_page_url(
    page: Page,
    observations: dict[str, object],
    key: str,
) -> None:
    try:
        observations[key] = page.url
    except Exception as error:
        observations[f"{key}_error_type"] = type(error).__name__


def _observe_scroll_position(
    page: Page,
    observations: dict[str, object],
    key: str,
) -> None:
    try:
        scroll = observe_playwright_page(page).get("scroll")
        if not isinstance(scroll, dict):
            raise TypeError("Playwright scroll observation must be an object")
        observations[key] = dict(scroll)
    except Exception as error:
        observations[f"{key}_error_type"] = type(error).__name__


def _verification_for_action(
    page: Page,
    action: PlaywrightAction,
) -> Callable[[], VerificationResult] | None:
    if isinstance(action.expectation, TextExpectation):
        return expect_text(page, action.expectation)
    if isinstance(action.expectation, VisibilityExpectation):
        return expect_visible(page, action.expectation)
    if isinstance(action.expectation, InputValueExpectation):
        selector = action.arguments.get("selector")
        text = action.arguments.get("text")
        if not isinstance(selector, str) or not selector.strip():
            raise ValueError("fill actions require a non-empty selector")
        if not isinstance(text, str):
            raise ValueError("fill actions require text")
        return expect_input_value(
            page,
            selector,
            text,
            action.expectation,
        )
    return None


class RecordedPlaywrightExecutor:
    def __init__(
        self,
        page: Page,
        output_dir: Path,
        *,
        goal: str | None = None,
        task_verification: Callable[[], VerificationResult] | None = None,
    ) -> None:
        self.page = page
        self.recorder = SessionRecorder(
            output_dir,
            self._capture_screenshot,
            goal=goal,
            task_verification=task_verification,
        )

    @property
    def session(self) -> ActionSession:
        return self.recorder.session

    @property
    def report_path(self) -> Path:
        return self.recorder.output_dir / "report.html"

    def __enter__(self) -> Self:
        self.recorder.__enter__()
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.recorder.__exit__(exception_type, exception, traceback)

    def execute(self, action: PlaywrightAction) -> ActionRecord:
        if not isinstance(action, PlaywrightAction):
            raise TypeError("action must be a PlaywrightAction")
        return record_playwright_action(
            self.page,
            self.recorder,
            action.action_type,
            action.arguments,
            verification=_verification_for_action(self.page, action),
        )

    def navigate(
        self,
        url: str,
        *,
        timeout_ms: int | None = None,
        expectation: (
            TextExpectation | VisibilityExpectation | None
        ) = None,
    ) -> ActionRecord:
        arguments: dict[str, object] = {"url": url}
        if timeout_ms is not None:
            arguments["timeout_ms"] = timeout_ms
        return self.execute(
            PlaywrightAction(
                "navigate",
                arguments,
                expectation=expectation,
            )
        )

    def click(
        self,
        selector: str,
        *,
        timeout_ms: int | None = None,
        expectation: (
            TextExpectation | VisibilityExpectation | None
        ) = None,
    ) -> ActionRecord:
        arguments: dict[str, object] = {"selector": selector}
        if timeout_ms is not None:
            arguments["timeout_ms"] = timeout_ms
        return self.execute(
            PlaywrightAction(
                "click",
                arguments,
                expectation=expectation,
            )
        )

    def fill(
        self,
        selector: str,
        text: str,
        *,
        timeout_ms: int | None = None,
        expectation: (
            TextExpectation
            | VisibilityExpectation
            | InputValueExpectation
            | None
        ) = None,
    ) -> ActionRecord:
        arguments: dict[str, object] = {
            "selector": selector,
            "text": text,
        }
        if timeout_ms is not None:
            arguments["timeout_ms"] = timeout_ms
        return self.execute(
            PlaywrightAction(
                "fill",
                arguments,
                expectation=expectation,
            )
        )

    def press(
        self,
        selector: str,
        key: str,
        *,
        timeout_ms: int | None = None,
        expectation: (
            TextExpectation | VisibilityExpectation | None
        ) = None,
    ) -> ActionRecord:
        arguments: dict[str, object] = {
            "selector": selector,
            "key": key,
        }
        if timeout_ms is not None:
            arguments["timeout_ms"] = timeout_ms
        return self.execute(
            PlaywrightAction(
                "press",
                arguments,
                expectation=expectation,
            )
        )

    def scroll(
        self,
        delta_y: int | float,
        *,
        delta_x: int | float = 0,
        expectation: (
            TextExpectation | VisibilityExpectation | None
        ) = None,
    ) -> ActionRecord:
        return self.execute(
            PlaywrightAction(
                "scroll",
                {"delta_x": delta_x, "delta_y": delta_y},
                expectation=expectation,
            )
        )

    def run(
        self,
        decide_next_action: Callable[[Page], PlaywrightAction | None],
        *,
        max_steps: int = 100,
    ) -> list[ActionRecord]:
        return run_playwright_agent(
            self.page,
            self.recorder,
            decide_next_action,
            max_steps=max_steps,
        )

    def _capture_screenshot(self, path: Path) -> None:
        self.page.screenshot(path=str(path), full_page=True)


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
    while True:
        next_action = decide_next_action(page)
        if next_action is None:
            return recorded_actions
        if len(recorded_actions) >= max_steps:
            raise RuntimeError(
                f"agent did not finish within {max_steps} steps"
            )
        if not isinstance(next_action, PlaywrightAction):
            raise TypeError(
                "decide_next_action must return a PlaywrightAction or None"
            )

        action = record_playwright_action(
            page,
            recorder,
            next_action.action_type,
            next_action.arguments,
            verification=_verification_for_action(page, next_action),
        )
        recorded_actions.append(action)
        if action.status is ActionStatus.FAILURE:
            return recorded_actions


def diagnose_playwright_click_failure(
    page: Page,
    action: ActionRecord,
) -> ActionRecord:
    if action.action_type != "click" or action.status is not ActionStatus.FAILURE:
        raise ValueError("only failed click actions can be diagnosed")

    selector = action.arguments.get("selector")
    if not isinstance(selector, str) or not selector.strip():
        raise ValueError("failed click actions require a non-empty selector")

    return _diagnose_playwright_target_failure(
        page,
        action,
        selector,
        check_editable=False,
    )


def diagnose_playwright_fill_failure(
    page: Page,
    action: ActionRecord,
) -> ActionRecord:
    if (
        action.action_type != "fill"
        or action.status is not ActionStatus.FAILURE
    ):
        raise ValueError("only failed fill actions can be diagnosed")

    selector = action.arguments.get("selector")
    if not isinstance(selector, str) or not selector.strip():
        raise ValueError("failed fill actions require a non-empty selector")

    return _diagnose_playwright_target_failure(
        page,
        action,
        selector,
        check_editable=True,
    )


def _diagnose_playwright_target_failure(
    page: Page,
    action: ActionRecord,
    selector: str,
    *,
    check_editable: bool,
) -> ActionRecord:
    evidence: dict[str, object] = {
        "selector": selector,
        "selector_count": None,
        "target_visible": None,
        "target_enabled": None,
    }
    if check_editable:
        evidence["target_editable"] = None
    category = action.failure_category

    try:
        locator = page.locator(selector)
        selector_count = locator.count()
        evidence["selector_count"] = selector_count

        if selector_count == 0:
            category = FailureCategory.TARGET_NOT_FOUND
        elif selector_count > 1:
            category = FailureCategory.TARGET_AMBIGUOUS
        elif selector_count == 1:
            target = locator.first
            target_visible = target.is_visible()
            target_enabled = target.is_enabled()
            evidence["target_visible"] = target_visible
            evidence["target_enabled"] = target_enabled
            target_editable = None
            if check_editable:
                target_editable = target.is_editable()
                evidence["target_editable"] = target_editable

            if not target_visible:
                category = FailureCategory.TARGET_NOT_VISIBLE
            elif not target_enabled:
                category = FailureCategory.TARGET_DISABLED
            elif check_editable and not target_editable:
                category = FailureCategory.TARGET_NOT_EDITABLE
    except Exception as error:
        evidence["diagnostic_error_type"] = type(error).__name__

    return replace(
        action,
        failure_category=category,
        failure_evidence={**action.failure_evidence, **evidence},
    )
