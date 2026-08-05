from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from agent_devtools.action import ActionStatus
from agent_devtools.integrations.playwright import (
    RecordedPlaywrightExecutor,
    ReplayStabilityStatus,
    evaluate_playwright_session_replay,
)
from agent_devtools.serialization import read_session_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "trace" / "browser-replay-stability"


def main() -> None:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    trace_dir = TRACE_ROOT / run_id
    source_dir = trace_dir / "original"
    evaluation_dir = trace_dir / "evaluation"
    page_path = Path(__file__).with_name("browser_diagnostics.html").resolve()
    task = "Open the diagnostics page and fill the missing input."

    with sync_playwright() as browser_api:
        browser = browser_api.chromium.launch(headless=True)
        try:
            source_page = browser.new_page(
                viewport={"width": 1000, "height": 650}
            )
            with RecordedPlaywrightExecutor(
                source_page,
                source_dir,
                goal=task,
            ) as executor:
                executor.navigate(page_path.as_uri())
                source_action = executor.fill(
                    "#missing-input",
                    "Agent debugging",
                    timeout_ms=100,
                )
            source_page.close()
            if source_action.status is not ActionStatus.FAILURE:
                raise RuntimeError("the source failure did not occur")

            source_session = read_session_json(source_dir / "session.json")
            evaluation = evaluate_playwright_session_replay(
                source_session,
                page_factory=lambda: browser.new_page(
                    viewport={"width": 1000, "height": 650}
                ),
                runs=3,
                output_dir=evaluation_dir,
            )
        finally:
            browser.close()

    if evaluation.status is not ReplayStabilityStatus.STABLE:
        raise RuntimeError(
            "the deterministic replay was not stable: "
            f"{evaluation.reproduced_count}/{evaluation.requested_runs}"
        )

    print(f"Original report: {source_dir / 'report.html'}")
    print(f"Stability report: {evaluation.report_path}")
    print(
        "Replay stability: "
        f"{evaluation.reproduced_count}/{evaluation.requested_runs} reproduced"
    )


if __name__ == "__main__":
    main()
