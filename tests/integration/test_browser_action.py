from pathlib import Path

import pytest

from agent_devtools.action import ActionStatus
from agent_devtools.recorder import record_action
from agent_devtools.serialization import read_action_json, write_action_json
from agent_devtools.verification import verify_text_state


playwright = pytest.importorskip(
    "playwright.sync_api",
    reason="the browser integration test requires the browser extra",
)


def test_records_real_browser_click(tmp_path: Path) -> None:
    page_path = (
        Path(__file__).parents[2] / "examples" / "browser_click.html"
    ).resolve()
    before_path = tmp_path / "before.png"
    after_path = tmp_path / "after.png"
    trace_path = tmp_path / "action.json"

    with playwright.sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 650})
        page.goto(page_path.as_uri())
        page.screenshot(path=str(before_path), full_page=True)

        action = record_action(
            action_type="click",
            arguments={"selector": "#agent-action"},
            operation=lambda: page.locator("#agent-action").click(),
            screenshot_before=Path("before.png"),
            screenshot_after=Path("after.png"),
        )

        page.screenshot(path=str(after_path), full_page=True)
        status_text = page.locator("#status").inner_text()
        browser.close()

    write_action_json(action, trace_path)
    verification = verify_text_state(
        expected_state="The browser click succeeded.",
        observed_state=status_text,
        evidence={"selector": "#status", "screenshot": "after.png"},
    )

    assert action.action_type == "click"
    assert action.arguments == {"selector": "#agent-action"}
    assert action.status is ActionStatus.SUCCESS
    assert action.duration_ms >= 0
    assert verification.passed
    assert verification.failure_reason is None
    assert before_path.stat().st_size > 0
    assert after_path.stat().st_size > 0
    assert before_path.read_bytes() != after_path.read_bytes()
    assert read_action_json(trace_path) == action
