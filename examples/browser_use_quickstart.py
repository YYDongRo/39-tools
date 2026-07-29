from __future__ import annotations

import asyncio

from browser_use import Agent, Browser, ChatGoogle

from agent_devtools.browser_use import observe_browser_use_agent


async def main() -> None:
    task = "Open https://example.com and confirm the Example Domain page is open."
    browser = Browser(
        headless=False,
        allowed_domains=["example.com"],
    )
    agent = observe_browser_use_agent(
        Agent(
            task=task,
            llm=ChatGoogle(model="gemini-2.5-flash"),
            browser=browser,
            use_judge=True,
        ),
        task,
    )

    try:
        await agent.run(max_steps=5)
        agent.assert_last_task_passed()
    finally:
        await browser.stop()

    assert agent.last_report_path is not None
    print(f"Report: {agent.last_report_path.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
