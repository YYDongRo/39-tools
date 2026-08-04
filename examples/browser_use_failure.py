from __future__ import annotations

import asyncio
from pathlib import Path

from browser_use import Agent, Browser, ChatGoogle

from agent_devtools.browser_use import (
    BrowserUseFinalStateCheck,
    observe_browser_use_agent,
)


async def main() -> None:
    task = "Open https://example.com and confirm the Example Domain page is open."
    browser = Browser(
        headless=False,
        allowed_domains=["example.com"],
    )
    raw_agent = Agent(
        task=task,
        llm=ChatGoogle(model="gemini-2.5-flash"),
        browser=browser,
        use_judge=True,
    )
    local_config = Path("agent_devtools.toml")
    agent = observe_browser_use_agent(
        raw_agent,
        config=local_config if local_config.is_file() else None,
        final_check=BrowserUseFinalStateCheck(
            title_contains="This title is intentionally absent",
        ),
    )

    try:
        await agent.run(max_steps=5)
    finally:
        await browser.stop()

    if agent.last_session is None or agent.last_session.verification is None:
        raise RuntimeError("the controlled failure demo was not verified")
    if agent.last_session.verification.passed:
        raise RuntimeError("the controlled failure demo unexpectedly passed")

    print("Expected task result: FAILURE")
    print(f"Actions recorded: {agent.last_session.action_count}")
    print(f"Report: {agent.last_report_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
