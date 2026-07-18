from pathlib import Path

from playwright.sync_api import sync_playwright

from agent_devtools.action import ActionStatus
from agent_devtools.recorder import record_action
from agent_devtools.report import write_action_html
from agent_devtools.serialization import write_action_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_DIR = PROJECT_ROOT / "trace" / "browser-failure"


def main() -> None:
    page_path = Path(__file__).with_name("browser_click.html").resolve()
    before_path = TRACE_DIR / "before.png"
    after_path = TRACE_DIR / "after.png"
    trace_path = TRACE_DIR / "action.json"
    report_path = TRACE_DIR / "report.html"
    selector = "#missing-agent-action"
    timeout_ms = 500
    TRACE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 650})
        page.goto(page_path.as_uri())
        page.screenshot(path=str(before_path), full_page=True)

        action = record_action(
            action_type="click",
            arguments={"selector": selector, "timeout_ms": timeout_ms},
            operation=lambda: page.locator(selector).click(timeout=timeout_ms),
            screenshot_before=Path("before.png"),
            screenshot_after=Path("after.png"),
        )

        page.screenshot(path=str(after_path), full_page=True)
        write_action_json(action, trace_path)
        write_action_html(action, report_path)
        browser.close()

    if action.status is not ActionStatus.FAILURE:
        raise RuntimeError("the controlled browser action did not fail")

    print(f"Failed browser action trace written to {TRACE_DIR}")


if __name__ == "__main__":
    main()
