from argparse import ArgumentParser
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright

from agent_devtools import (
    ActionOutcome,
    VerificationResult,
    record_tools,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "trace" / "youtube-agent"
YOUTUBE_URL = "https://www.youtube.com/?hl=en"
SEARCH_INPUT = "input[name='search_query']:visible"
SEARCH_BUTTON = (
    "button.ytSearchboxComponentSearchButton:visible, "
    "button#search-icon-legacy:visible"
)
FIRST_VIDEO_RESULT = "ytd-video-renderer a#video-title >> nth=0"
VIDEO_PLAYER = "video.html5-main-video >> nth=0"


class YouTubeTools:
    def __init__(self, page: Page) -> None:
        self.page = page

    def navigate(self, url: str, timeout_ms: int) -> None:
        self.page.goto(url, timeout=timeout_ms)

    def fill(self, selector: str, text: str, timeout_ms: int) -> None:
        self.page.locator(selector).fill(text, timeout=timeout_ms)

    def click(
        self,
        selector: str,
        timeout_ms: int,
        *,
        wait_for: str | None = None,
    ) -> None:
        self.page.locator(selector).click(timeout=timeout_ms)
        if wait_for is not None:
            self.page.locator(wait_for).wait_for(
                state="visible",
                timeout=timeout_ms,
            )


def run_agent(
    page: Page,
    tools: YouTubeTools,
    query: str,
    *,
    max_steps: int = 4,
) -> None:
    completed_steps = 0
    while True:
        parsed_url = urlparse(page.url)
        if parsed_url.path == "/watch":
            return

        if completed_steps >= max_steps:
            raise RuntimeError(
                f"agent did not finish within {max_steps} steps"
            )

        if parsed_url.hostname not in {"youtube.com", "www.youtube.com"}:
            tools.navigate(YOUTUBE_URL, timeout_ms=30_000)
        elif parsed_url.path == "/results":
            if not page.locator(FIRST_VIDEO_RESULT).is_visible():
                return
            tools.click(
                FIRST_VIDEO_RESULT,
                timeout_ms=20_000,
                wait_for=VIDEO_PLAYER,
            )
        else:
            search_input = page.locator(SEARCH_INPUT)
            if (
                search_input.count() == 1
                and search_input.input_value() != query
            ):
                tools.fill(SEARCH_INPUT, query, timeout_ms=10_000)
            elif search_input.count() == 1:
                tools.click(
                    SEARCH_BUTTON,
                    timeout_ms=20_000,
                    wait_for=FIRST_VIDEO_RESULT,
                )
            else:
                return

        completed_steps += 1


def verify_task(page: Page) -> VerificationResult:
    current_url = page.url
    player = page.locator(VIDEO_PLAYER)
    player_count = player.count()
    player_visible = player_count > 0 and player.first.is_visible()
    on_watch_page = urlparse(current_url).path == "/watch"
    passed = on_watch_page and player_visible
    observed_state = (
        f"watch_page={on_watch_page}, visible_player={player_visible}"
    )

    return VerificationResult(
        expected_state="a YouTube watch page with a visible video player",
        observed_state=observed_state,
        passed=passed,
        evidence={
            "url": current_url,
            "player_count": player_count,
            "player_visible": player_visible,
        },
        failure_reason=(
            None
            if passed
            else (
                "the agent did not reach a YouTube watch page with a "
                "visible player"
            )
        ),
    )


def parse_args() -> tuple[str, bool]:
    parser = ArgumentParser(description="Trace a live YouTube search task")
    parser.add_argument(
        "--query",
        default="computer use agents",
        help="YouTube search query",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="show the browser while the demo runs",
    )
    args = parser.parse_args()
    return args.query, args.headed


def main() -> None:
    query, headed = parse_args()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    trace_dir = TRACE_ROOT / run_id
    goal = f"Search YouTube for {query!r} and open a video result"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        context = browser.new_context(
            locale="en-US",
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        trace = record_tools(
            YouTubeTools(page),
            trace_dir,
            capture_screenshot=lambda path: page.screenshot(
                path=str(path),
                full_page=True,
            ),
            goal=goal,
            task_verification=lambda: verify_task(page),
        )
        with trace as tools:
            run_agent(page, tools, query)

        context.close()
        browser.close()

    print(f"Recorded actions: {trace.session.action_count}")
    print(f"Final task outcome: {trace.session.outcome.value}")
    print(f"Report: {trace.report_path.resolve()}")

    if trace.session.outcome is not ActionOutcome.SUCCESS:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
