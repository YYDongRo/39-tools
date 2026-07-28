import asyncio
from datetime import UTC, datetime
from pathlib import Path

from agent_devtools import VerificationResult, record_async_tools


class AsyncBrowserTools:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.query = ""

    async def navigate(self, url: str) -> None:
        await asyncio.sleep(0.01)
        self.url = url

    async def fill(self, selector: str, value: str) -> None:
        await asyncio.sleep(0.01)
        self.query = value


async def main() -> None:
    raw_tools = AsyncBrowserTools()
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
    trace = record_async_tools(
        raw_tools,
        Path("trace") / "async-tools" / run_id,
        observe_state=lambda: {
            "url": raw_tools.url,
            "query": raw_tools.query,
        },
        goal="open search and enter agent debugging",
        task_verification=lambda: VerificationResult(
            expected_state="search page contains query",
            observed_state=(
                f"url={raw_tools.url}, query={raw_tools.query}"
            ),
            passed=(
                raw_tools.url == "https://example.com/search"
                and raw_tools.query == "agent debugging"
            ),
            failure_reason=(
                None
                if raw_tools.url == "https://example.com/search"
                and raw_tools.query == "agent debugging"
                else "the final simulated browser state did not match"
            ),
        ),
    )

    async with trace as tools:
        await tools.navigate("https://example.com/search")
        await tools.fill("#search", "agent debugging")

    print(f"Final outcome: {trace.session.outcome.value}")
    print(f"Report: {trace.report_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
