"""Run one Browser Use task entered in a terminal and print its report."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Literal

from browser_use import Agent, Browser, ChatGoogle, ChatOpenAI

from agent_devtools.browser_use import observe_browser_use_agent
from agent_devtools.config import AgentDevToolsConfig


Provider = Literal["auto", "gemini", "openai"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one Browser Use task and create an Agent DevTools report."
    )
    parser.add_argument(
        "--task",
        help="task to run; prompt interactively when omitted",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=(
            "Agent DevTools TOML path (default: agent_devtools.toml if present)"
        ),
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=10,
        help="maximum Browser Use steps (default: 10)",
    )
    parser.add_argument(
        "--provider",
        choices=("auto", "gemini", "openai"),
        default="auto",
        help=(
            "LLM provider; auto detects the only configured key "
            "(default: auto)"
        ),
    )
    parser.add_argument(
        "--model",
        help="optional provider model; otherwise use the example default",
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


def _load_config(path: Path | None = None) -> AgentDevToolsConfig | None:
    config_path = path or Path("agent_devtools.toml")
    if not config_path.is_file():
        if path is not None:
            raise FileNotFoundError(
                f"Agent DevTools config does not exist: {config_path}"
            )
        return None
    return AgentDevToolsConfig.from_file(config_path)


def _browser_kwargs(
    config: AgentDevToolsConfig | None,
    *,
    headed: bool,
) -> dict[str, object]:
    kwargs: dict[str, object] = {"headless": not headed}
    if config is None or config.browser_executable_path is None:
        return kwargs

    executable_path = config.browser_executable_path
    if not executable_path.is_file():
        raise ValueError(
            "configured browser executable was not found: "
            f"{executable_path}"
        )
    kwargs["executable_path"] = str(executable_path)
    return kwargs


def _resolve_provider(requested: Provider) -> Literal["gemini", "openai"]:
    provider = requested
    if provider == "auto":
        provider = os.getenv("AGENT_DEVTOOLS_LLM_PROVIDER", "auto").strip().lower()

    if provider in {"gemini", "openai"}:
        return provider
    if provider != "auto":
        raise ValueError(
            "AGENT_DEVTOOLS_LLM_PROVIDER must be 'gemini' or 'openai'"
        )

    configured = []
    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        configured.append("gemini")
    if os.getenv("OPENAI_API_KEY"):
        configured.append("openai")

    if len(configured) == 1:
        return configured[0]  # type: ignore[return-value]
    if not configured:
        raise ValueError(
            "set GOOGLE_API_KEY or GEMINI_API_KEY for Gemini, "
            "or OPENAI_API_KEY for OpenAI"
        )
    raise ValueError(
        "multiple provider keys are set; pass --provider gemini or "
        "--provider openai"
    )


def _create_llm(provider: Literal["gemini", "openai"], model: str | None) -> object:
    if provider == "gemini":
        key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("set GOOGLE_API_KEY or GEMINI_API_KEY for Gemini")
        return ChatGoogle(model=model or "gemini-2.5-flash", api_key=key)

    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("set OPENAI_API_KEY for OpenAI")
    return ChatOpenAI(model=model or "gpt-4o", api_key=key)


async def main() -> int:
    args = _parser().parse_args()
    task = (args.task or input("Task: ")).strip()
    if not task:
        print("Task cannot be empty.")
        return 2

    try:
        provider = _resolve_provider(args.provider)
        llm = _create_llm(provider, args.model)
    except ValueError as error:
        print(f"Configuration error: {error}")
        return 2

    try:
        config = _load_config(args.config)
    except (FileNotFoundError, TypeError, ValueError) as error:
        print(f"Configuration error: {error}")
        return 2
    try:
        browser = Browser(**_browser_kwargs(config, headed=args.headed))
    except (OSError, ValueError) as error:
        print(f"Configuration error: {error}")
        return 2
    raw_agent = Agent(
        task=task,
        llm=llm,
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
