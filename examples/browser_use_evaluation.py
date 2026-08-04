"""Run the same Browser Use task several times and create one local report.

This is a product-shaped example rather than a test fixture. It uses a fresh
Browser Use Agent for every attempt, preserves each normal trace, and returns
exit code 1 when any requested run is not explicitly passed.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from browser_use import Agent, Browser, ChatGoogle

from agent_devtools.browser_use import (
    AgentEvaluation,
    BrowserUseFinalStateCheck,
    evaluate_browser_use_agent,
)
from agent_devtools.config import AgentDevToolsConfig


DEFAULT_TASK = "Open https://example.com and confirm the Example Domain page is open."


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate a Browser Use task across fresh local runs."
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="number of sequential attempts (default: 3)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=8,
        help="maximum Browser Use steps per attempt (default: 8)",
    )
    parser.add_argument(
        "--task",
        default=DEFAULT_TASK,
        help="task to repeat (default: Example Domain check)",
    )
    parser.add_argument(
        "--title-contains",
        default="Example Domain",
        help="required text in the final page title (default: Example Domain)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="override the evaluation directory from agent_devtools.toml",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="show the browser while the attempts run",
    )
    parser.add_argument(
        "--open-report",
        action="store_true",
        help="open the aggregate report after the run",
    )
    return parser


def _load_local_config() -> AgentDevToolsConfig | None:
    path = Path("agent_devtools.toml")
    return AgentDevToolsConfig.from_file(path) if path.is_file() else None


def _print_summary(evaluation: AgentEvaluation) -> None:
    result = "PASS" if evaluation.all_runs_passed else "FAIL"
    print("Agent DevTools stability evaluation")
    print(f"Result: {result}")
    print(
        "Runs: "
        f"{evaluation.requested_run_count} requested, "
        f"{evaluation.passed_count} passed, "
        f"{evaluation.failed_count} failed, "
        f"{evaluation.unverified_count} unverified, "
        f"{evaluation.errored_count} errored"
    )
    print(f"Pass rate: {evaluation.empirical_pass_rate:.1%}")
    print(f"Report: {evaluation.report_path.resolve()}")


async def main() -> int:
    args = _parser().parse_args()
    config = _load_local_config()

    def create_agent(task: str) -> Agent:
        return Agent(
            task=task,
            llm=ChatGoogle(model="gemini-2.5-flash"),
            browser=Browser(
                headless=not args.headed,
                allowed_domains=["example.com"],
            ),
            use_judge=True,
        )

    evaluation = await evaluate_browser_use_agent(
        agent_factory=create_agent,
        task=args.task,
        runs=args.runs,
        max_steps=args.max_steps,
        output_root=args.output_root,
        config=config,
        final_check=BrowserUseFinalStateCheck(
            title_contains=args.title_contains,
        ),
    )
    _print_summary(evaluation)

    if args.open_report and not (config is not None and config.open_report):
        try:
            evaluation.open_report()
        except Exception as error:
            print(
                "Report could not be opened automatically: "
                f"{type(error).__name__}. Open the printed path manually."
            )

    if not evaluation.all_runs_passed:
        print("CI result: failed because not every run was explicitly passed.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
