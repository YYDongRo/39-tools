"""Command-line entry points for the supported Agent DevTools workflows."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Literal, Sequence

from agent_devtools.action import ActionStatus
from agent_devtools.browser_use import observe_browser_use_agent
from agent_devtools.config import AgentDevToolsConfig
from agent_devtools.serialization import _write_json
from agent_devtools.session import ActionSession


Provider = Literal["auto", "gemini", "openai"]
SummaryStatus = Literal["passed", "failed", "unverified", "errored"]


def _browser_use_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-devtools",
        description="Run one Browser Use task and create an Agent DevTools report.",
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
    parser.add_argument(
        "--summary-json",
        type=Path,
        help=(
            "write a concise versioned CI summary JSON to this path; "
            "the full report is still generated"
        ),
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


def _create_llm(
    provider: Literal["gemini", "openai"],
    model: str | None,
) -> object:
    if provider == "gemini":
        from browser_use import ChatGoogle

        key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("set GOOGLE_API_KEY or GEMINI_API_KEY for Gemini")
        return ChatGoogle(model=model or "gemini-2.5-flash", api_key=key)

    from browser_use import ChatOpenAI

    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("set OPENAI_API_KEY for OpenAI")
    return ChatOpenAI(model=model or "gpt-4o", api_key=key)


def _summary_path(path: Path | None) -> str | None:
    if path is None:
        return None
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved_path.as_posix()


def _summary_status(
    session: ActionSession | None,
    *,
    run_error: BaseException | None = None,
) -> SummaryStatus:
    if run_error is not None:
        return "errored"
    if session is None or session.verification is None:
        return "unverified"
    return "passed" if session.verification.passed else "failed"


def _build_summary(
    *,
    status: SummaryStatus,
    report_path: Path | None,
    session: ActionSession | None = None,
    error_type: str | None = None,
) -> dict[str, object]:
    actions = session.actions if session is not None else []
    verification = session.verification if session is not None else None
    return {
        "schema_version": 1,
        "status": status,
        "action_count": len(actions),
        "action_success_count": sum(
            action.status is ActionStatus.SUCCESS for action in actions
        ),
        "action_failure_count": sum(
            action.status is ActionStatus.FAILURE for action in actions
        ),
        "final_check": (
            "not_run"
            if verification is None
            else "passed"
            if verification.passed
            else "failed"
        ),
        "report_path": _summary_path(report_path),
        "session_path": (
            _summary_path(report_path.parent / "session.json")
            if report_path is not None
            else None
        ),
        "error_type": error_type,
    }


def _write_summary(
    path: Path | None,
    *,
    status: SummaryStatus,
    report_path: Path | None,
    session: ActionSession | None = None,
    error_type: str | None = None,
) -> None:
    if path is None:
        return
    _write_json(
        _build_summary(
            status=status,
            report_path=report_path,
            session=session,
            error_type=error_type,
        ),
        path,
    )
    print(f"Summary: {path.resolve()}")


def _write_errored_summary(
    path: Path | None,
    error_type: str,
    *,
    report_path: Path | None = None,
    session: ActionSession | None = None,
) -> None:
    _write_summary(
        path,
        status="errored",
        report_path=report_path,
        session=session,
        error_type=error_type,
    )


async def _browser_use_main(argv: Sequence[str] | None = None) -> int:
    args = _browser_use_parser().parse_args(argv)
    task = (args.task or input("Task: ")).strip()
    if not task:
        print("Task cannot be empty.")
        _write_errored_summary(args.summary_json, "ValueError")
        return 2

    try:
        from browser_use import Agent, Browser
    except ImportError:
        print(
            "Browser Use is not installed. Install the optional integration "
            "with: uv add '39-tools[browser-use] @ "
            "git+https://github.com/YYDongRo/39-tools.git'"
        )
        _write_errored_summary(args.summary_json, "ImportError")
        return 2

    try:
        provider = _resolve_provider(args.provider)
        llm = _create_llm(provider, args.model)
    except ValueError as error:
        print(f"Configuration error: {error}")
        _write_errored_summary(args.summary_json, type(error).__name__)
        return 2

    try:
        config = _load_config(args.config)
    except (FileNotFoundError, TypeError, ValueError) as error:
        print(f"Configuration error: {error}")
        _write_errored_summary(args.summary_json, type(error).__name__)
        return 2
    try:
        browser = Browser(**_browser_kwargs(config, headed=args.headed))
    except (OSError, ValueError) as error:
        print(f"Configuration error: {error}")
        _write_errored_summary(args.summary_json, type(error).__name__)
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
        _write_errored_summary(
            args.summary_json,
            "ReportNotCreated",
            session=agent.last_session,
        )
        return 1

    print(f"Report: {report_path.resolve()}")
    if run_error is not None:
        print(f"Agent run failed: {type(run_error).__name__}")
        _write_errored_summary(
            args.summary_json,
            type(run_error).__name__,
            report_path=report_path,
            session=agent.last_session,
        )
        return 1

    try:
        agent.assert_last_task_passed()
    except AssertionError as error:
        print(f"Task result: FAIL — {error}")
        result_is_verified = False
    else:
        print("Task result: PASS")
        result_is_verified = True

    _write_summary(
        args.summary_json,
        status=_summary_status(agent.last_session),
        report_path=report_path,
        session=agent.last_session,
    )

    if args.open_report and not (config is not None and config.open_report):
        try:
            agent.open_last_report()
        except Exception as error:
            print(f"Report could not be opened: {type(error).__name__}")

    return 0 if result_is_verified else 1


def main() -> int:
    """Run the installed Browser Use command-line workflow."""

    return asyncio.run(_browser_use_main())


__all__ = ["main"]
