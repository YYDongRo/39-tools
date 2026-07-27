from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from agent_devtools import ActionOutcome
from agent_devtools.playwright import (
    RecordedPlaywrightExecutor,
    TextExpectation,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "trace" / "quickstart"


def main() -> None:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    trace_dir = TRACE_ROOT / run_id

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1000, "height": 650})
        page.set_content(
            """
            <button id="save" type="button">Save</button>
            <p id="status">Not saved</p>
            <script>
              document.querySelector("#save").addEventListener("click", () => {
                document.querySelector("#status").textContent = "Saved";
              });
            </script>
            """
        )

        with RecordedPlaywrightExecutor(page, trace_dir) as executor:
            action = executor.click(
                "#save",
                expectation=TextExpectation("#status", "Saved"),
            )

        browser.close()

    if action.outcome is not ActionOutcome.SUCCESS:
        raise RuntimeError("the quickstart action was not verified")

    print(f"Final outcome: {action.outcome.value}")
    print(f"Report: {executor.report_path.resolve()}")


if __name__ == "__main__":
    main()
