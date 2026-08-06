"""Run the same Browser Use task several times and create one local report.

This is a product-shaped example rather than a test fixture. It uses a fresh
Browser Use Agent for every attempt, preserves each normal trace, and returns
exit code 1 when any requested run is not explicitly passed. Use
``--allowed-domain`` and the optional URL/title checks for a site other than
the default Example Domain demo.
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
DEFAULT_ALLOWED_DOMAIN = "example.com"


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
        "--config",
        type=Path,
        default=None,
        help=(
            "Agent DevTools TOML path (default: agent_devtools.toml if present)"
        ),
    )
    parser.add_argument(
        "--allowed-domain",
        action="append",
        dest="allowed_domains",
        metavar="DOMAIN",
        help=(
            "domain the browser may visit; repeat for multiple domains "
            f"(default: {DEFAULT_ALLOWED_DOMAIN})"
        ),
    )
    parser.add_argument(
        "--title-contains",
        default=None,
        help="optional text required in the final page title",
    )
    parser.add_argument(
        "--url-contains",
        default=None,
        help="optional text required in the final page URL",
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


def _load_local_config(path: Path | None = None) -> AgentDevToolsConfig | None:
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
    allowed_domains: list[str] | None = None,
) -> dict[str, object]:
    if allowed_domains is None:
        domains = [DEFAULT_ALLOWED_DOMAIN]
    else:
        domains = [domain.strip() for domain in allowed_domains]
        if not domains or any(not domain for domain in domains):
            raise ValueError("allowed domains cannot be empty")

    kwargs: dict[str, object] = {
        "headless": not headed,
        "allowed_domains": domains,
    }
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


def _final_check(
    *,
    url_contains: str | None,
    title_contains: str | None,
) -> BrowserUseFinalStateCheck | None:
    if url_contains is None and title_contains is None:
        return None
    return BrowserUseFinalStateCheck(
        url_contains=url_contains,
        title_contains=title_contains,
    )


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
    if evaluation.comparison_report_path is not None:
        print(
            "Comparison: "
            f"{evaluation.comparison_report_path.resolve()}"
        )


async def main() -> int:
    args = _parser().parse_args()
    try:
        config = _load_local_config(args.config)
    except (FileNotFoundError, TypeError, ValueError) as error:
        print(f"Configuration error: {error}")
        return 2

    try:
        browser_kwargs = _browser_kwargs(
            config,
            headed=args.headed,
            allowed_domains=args.allowed_domains,
        )
    except ValueError as error:
        print(f"Configuration error: {error}")
        return 2

    def create_agent(task: str) -> Agent:
        return Agent(
            task=task,
            llm=ChatGoogle(model="gemini-2.5-flash"),
            browser=Browser(**browser_kwargs),
            use_judge=True,
        )

    evaluation = await evaluate_browser_use_agent(
        agent_factory=create_agent,
        task=args.task,
        runs=args.runs,
        max_steps=args.max_steps,
        output_root=args.output_root,
        config=config,
        final_check=_final_check(
            url_contains=args.url_contains,
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
