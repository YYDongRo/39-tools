"""Run one Browser Use task entered in a terminal and print its report."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from browser_use import Agent, Browser, ChatGoogle

from agent_devtools.browser_use import observe_browser_use_agent
from agent_devtools.config import AgentDevToolsConfig


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one Browser Use task and create an Agent DevTools report."
    )
    parser.add_argument(
        "--task",
        help="task to run; prompt interactively when omitted",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=10,
        help="maximum Browser Use steps (default: 10)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="show the browser while the task runs",
    )
    parser.add_argument(
        "--open-report",
        action="store_true",
        help="open the report after the task finishes",
    )
    return parser


def _load_config() -> AgentDevToolsConfig | None:
    path = Path("agent_devtools.toml")
    return AgentDevToolsConfig.from_file(path) if path.is_file() else None


async def main() -> int:
    args = _parser().parse_args()
    task = (args.task or input("Task: ")).strip()
    if not task:
        print("Task cannot be empty.")
        return 2

    config = _load_config()
    browser = Browser(headless=not args.headed)
    raw_agent = Agent(
        task=task,
        llm=ChatGoogle(model="gemini-2.5-flash"),
        browser=browser,
        use_judge=True,
    )
    agent = observe_browser_use_agent(raw_agent, config=config)

    run_error: Exception | None = None
    try:
        await agent.run(max_steps=args.max_steps)
    except Exception as error:
        run_error = error
    finally:
        await browser.stop()

    report_path = agent.last_report_path
    if report_path is None:
        print("No report was created.")
        return 1

    print(f"Report: {report_path.resolve()}")
    if run_error is not None:
        print(f"Agent run failed: {type(run_error).__name__}")
        return 1

    try:
        agent.assert_last_task_passed()
    except AssertionError as error:
        print(f"Task result: FAIL — {error}")
        result_is_verified = False
    else:
        print("Task result: PASS")
        result_is_verified = True

    if args.open_report and not (config is not None and config.open_report):
        try:
            agent.open_last_report()
        except Exception as error:
            print(f"Report could not be opened: {type(error).__name__}")

    return 0 if result_is_verified else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
