from collections.abc import Callable
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from agent_devtools.action import ActionStatus
from agent_devtools.recorder import record_action
from agent_devtools.report import write_session_html
from agent_devtools.serialization import write_session_json
from agent_devtools.session import ActionSession


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_DIR = PROJECT_ROOT / "trace" / "browser-session"


def record_page_action(
    page: Page,
    session: ActionSession,
    index: int,
    action_type: str,
    arguments: dict[str, object],
    operation: Callable[[], object],
) -> None:
    action_dir = Path("actions") / f"{index:03d}"
    output_dir = TRACE_DIR / action_dir
    before_path = action_dir / "before.png"
    after_path = action_dir / "after.png"
    output_dir.mkdir(parents=True, exist_ok=True)

    page.screenshot(path=str(TRACE_DIR / before_path), full_page=True)
    action = record_action(
        action_type=action_type,
        arguments=arguments,
        operation=operation,
        screenshot_before=before_path,
        screenshot_after=after_path,
    )
    page.screenshot(path=str(TRACE_DIR / after_path), full_page=True)
    session.actions.append(action)


def main() -> None:
    page_path = Path(__file__).with_suffix(".html").resolve()
    session = ActionSession()
    TRACE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 700})
        page.goto(page_path.as_uri())

        record_page_action(
            page=page,
            session=session,
            index=1,
            action_type="click",
            arguments={"selector": "#open-panel"},
            operation=lambda: page.locator("#open-panel").click(),
        )
        record_page_action(
            page=page,
            session=session,
            index=2,
            action_type="fill",
            arguments={"selector": "#task-name", "text": "Debug agent run"},
            operation=lambda: page.locator("#task-name").fill("Debug agent run"),
        )
        record_page_action(
            page=page,
            session=session,
            index=3,
            action_type="click",
            arguments={"selector": "#missing-confirm-action", "timeout_ms": 500},
            operation=lambda: page.locator("#missing-confirm-action").click(
                timeout=500
            ),
        )
        browser.close()

    write_session_json(session, TRACE_DIR / "session.json")
    write_session_html(session, TRACE_DIR / "report.html")

    expected_statuses = [
        ActionStatus.SUCCESS,
        ActionStatus.SUCCESS,
        ActionStatus.FAILURE,
    ]
    if [action.status for action in session.actions] != expected_statuses:
        raise RuntimeError("the browser session did not produce the expected statuses")

    print(f"Browser session trace written to {TRACE_DIR}")


if __name__ == "__main__":
    main()
