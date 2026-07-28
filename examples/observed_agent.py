from pathlib import Path

from agent_devtools.playwright import (
    TaskExpectation,
    all_of,
    element_visible,
    observe_playwright_agent,
    text_contains,
    url_matches,
)


TARGET_URL = (
    Path(__file__).parent / "browser_diagnostics.html"
).resolve().as_uri()


class BrowserTools:
    def __init__(self, page: object) -> None:
        self.page = page

    def navigate(self, url: str) -> None:
        self.page.goto(url)  # type: ignore[attr-defined]

    def click(self, selector: str) -> None:
        self.page.locator(selector).click()  # type: ignore[attr-defined]


class DemoAgent:
    def run(self, user_request: str, *, tools: BrowserTools) -> str:
        tools.navigate(TARGET_URL)
        if "click" in user_request.lower():
            tools.click("#visible-target")
        return "done"


def demo_expectation_generator(user_request: str) -> TaskExpectation:
    checks = [
        url_matches(scheme="file"),
        element_visible("#visible-target"),
    ]
    if "diagnostics" in user_request.lower():
        checks.append(text_contains("h1", "Browser action diagnostics"))
    return all_of(*checks)


def main() -> None:
    from playwright.sync_api import sync_playwright

    user_request = "Open the browser diagnostics and click the visible target"

    with sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page()
        agent = observe_playwright_agent(
            DemoAgent(),
            BrowserTools(page),
            page,
            Path("trace") / "observed-agent",
            expectation_generator=demo_expectation_generator,
        )

        result = agent.run(user_request)
        agent.assert_last_task_passed()
        browser.close()

    print(f"Agent result: {result}")
    print(f"Report: {agent.last_report_path.resolve()}")


if __name__ == "__main__":
    main()
