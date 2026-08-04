"""Run a deterministic agent through the framework-independent observer."""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_devtools import VerificationResult, observe_agent


TASK = "Open the local demo page and click the action button."
TARGET_URL = (Path(__file__).parent / "browser_click.html").resolve().as_uri()


class BrowserTools:
    def __init__(self, page: object) -> None:
        self.page = page

    def navigate(self, url: str) -> None:
        self.page.goto(url)  # type: ignore[attr-defined]

    def click(self, selector: str) -> None:
        self.page.locator(selector).click()  # type: ignore[attr-defined]


class DemoAgent:
    def __init__(self, task: str) -> None:
        self.task = task

    def run(self, task: str, *, tools: BrowserTools) -> str:
        if task != self.task:
            raise ValueError("the observer passed a different task")
        tools.navigate(TARGET_URL)
        tools.click("#agent-action")
        return "done"


def _state(page: object) -> dict[str, object]:
    return page.evaluate(  # type: ignore[attr-defined]
        """() => ({
            url: window.location.href,
            title: document.title,
            status: document.querySelector('#status')?.textContent ?? '',
            button: document.querySelector('#agent-action')?.textContent ?? '',
            disabled: document.querySelector('#agent-action')?.disabled ?? false,
        })"""
    )


def _verify(page: object) -> VerificationResult:
    state = _state(page)
    status = str(state.get("status", ""))
    passed = status == "The browser click succeeded."
    return VerificationResult(
        expected_state="The browser click succeeded.",
        observed_state=status,
        passed=passed,
        failure_reason=None if passed else f"observed status: {status!r}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a real browser action through observe_agent()."
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="show the browser while the demo runs",
    )
    parser.add_argument(
        "--open-report",
        action="store_true",
        help="open the generated report after the run",
    )
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    observed = None
    failure: Exception | None = None
    result: object = None

    with sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=not args.headed)
        page = browser.new_page()
        raw_agent = DemoAgent(TASK)
        observed = observe_agent(
            raw_agent,
            BrowserTools(page),
            Path("trace") / "generic-agent-browser",
            capture_screenshot=lambda path: page.screenshot(path=str(path)),
            observe_state=lambda: _state(page),
            task_verification=lambda: _verify(page),
        )

        try:
            result = observed.run()
            observed.assert_last_task_passed()
        except Exception as error:
            failure = error
        finally:
            browser.close()

    assert observed is not None
    report_path = observed.last_report_path
    print(f"Agent result: {result}")
    print(f"Task result: {'FAIL' if failure else 'PASS'}")
    print(f"Report: {report_path.resolve() if report_path else 'unavailable'}")

    if args.open_report and report_path is not None:
        try:
            observed.open_last_report()
        except Exception as error:
            print(
                "Report could not be opened automatically: "
                f"{type(error).__name__}. Open the printed path manually."
            )

    if failure is not None:
        print(f"Failure: {type(failure).__name__}: {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
