from pathlib import Path

import pytest

from agent_devtools import VerificationResult, observe_agent


playwright = pytest.importorskip(
    "playwright.sync_api",
    reason="the generic agent demo requires the browser extra",
)


TARGET_URL = (
    Path(__file__).parents[2] / "examples" / "browser_click.html"
).resolve().as_uri()


class BrowserTools:
    def __init__(self, page: object) -> None:
        self.page = page

    def navigate(self, url: str) -> None:
        self.page.goto(url)  # type: ignore[attr-defined]

    def click(self, selector: str) -> None:
        self.page.locator(selector).click()  # type: ignore[attr-defined]


class Agent:
    task = "Open the local demo page and click the action button."

    def run(self, task: str, *, tools: BrowserTools) -> str:
        assert task == self.task
        tools.navigate(TARGET_URL)
        tools.click("#agent-action")
        return "done"


def _state(page: object) -> dict[str, object]:
    return page.evaluate(  # type: ignore[attr-defined]
        """() => ({
            url: window.location.href,
            title: document.title,
            status: document.querySelector('#status')?.textContent ?? '',
        })"""
    )


def test_generic_agent_observer_records_real_browser_trajectory(
    tmp_path: Path,
) -> None:
    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        observed = observe_agent(
            Agent(),
            BrowserTools(page),
            tmp_path / "trace",
            capture_screenshot=lambda path: page.screenshot(path=str(path)),
            observe_state=lambda: _state(page),
            task_verification=lambda: VerificationResult(
                expected_state="The browser click succeeded.",
                observed_state=str(_state(page)["status"]),
                passed=(
                    _state(page)["status"]
                    == "The browser click succeeded."
                ),
                failure_reason=(
                    None
                    if _state(page)["status"]
                    == "The browser click succeeded."
                    else "the browser status did not confirm the click"
                ),
            ),
        )

        assert observed.run() == "done"
        observed.assert_last_task_passed()
        browser.close()

    assert observed.last_trace is not None
    session = observed.last_trace.session
    assert session.goal == Agent.task
    assert session.outcome.value == "success"
    assert [action.action_type for action in session.actions] == [
        "navigate",
        "click",
    ]
    assert all(
        action.screenshot_before is not None
        and action.screenshot_after is not None
        for action in session.actions
    )
    assert observed.last_report_path is not None
    assert observed.last_report_path.is_file()

