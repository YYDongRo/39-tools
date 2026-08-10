"""Command-line entry points for the supported Agent DevTools workflows."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Literal, Sequence

from agent_devtools.action import ActionStatus
from agent_devtools.browser_use import (
    AgentEvaluation,
    BrowserUsePreflightResult,
    evaluate_browser_use_agent,
    observe_browser_use_agent,
)
from agent_devtools.bundle import BundleExportError, export_diagnostic_bundle
from agent_devtools.config import AgentDevToolsConfig
from agent_devtools.control_center import serve_control_center
from agent_devtools.diagnostics import classify_run_issue
from agent_devtools.report_opening import open_local_report
from agent_devtools.run_index import write_run_index
from agent_devtools.serialization import _write_json
from agent_devtools.session import ActionSession


Provider = Literal["auto", "gemini", "openai"]
SummaryStatus = Literal["passed", "failed", "unverified", "errored"]


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _port(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a port number") from error
    if not 0 <= parsed <= 65535:
        raise argparse.ArgumentTypeError("must be between 0 and 65535")
    return parsed


def _browser_use_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-devtools",
        description=(
            "Run a Browser Use task and create an Agent DevTools report; "
            "use --runs for stability evaluation."
        ),
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
        "--runs",
        type=_positive_int,
        default=1,
        help=(
            "fresh sequential attempts; values above 1 create a stability "
            "evaluation (default: 1)"
        ),
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
        "--open-index",
        action="store_true",
        help="open the local run index after the task finishes",
    )
    parser.add_argument(
        "--export-bundle",
        action="store_true",
        help="export the completed trace as a dated diagnostic zip",
    )
    parser.add_argument(
        "--redact",
        action="store_true",
        help=(
            "redact common secrets and omit screenshots in the exported bundle"
        ),
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="check recording setup and exit without running the task",
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


def _control_center_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-devtools dashboard",
        description="Show the current local Agent DevTools run status.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("trace"),
        help=(
            "trace root to watch; recent observer roots are discovered below "
            "it (default: trace)"
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="local interface to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=_port,
        default=0,
        help="port to bind; 0 chooses a free local port (default: 0)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="open the control center in the default browser",
    )
    return parser


def _control_center_main(argv: Sequence[str] | None = None) -> int:
    args = _control_center_parser().parse_args(argv)
    try:
        serve_control_center(
            args.root,
            host=args.host,
            port=args.port,
            open_browser=args.open,
        )
    except (OSError, TypeError, ValueError) as error:
        print(f"Control center could not start: {type(error).__name__}: {error}")
        return 2
    return 0


def _load_config(path: Path | None = None) -> AgentDevToolsConfig | None:
    config_path = path or Path("agent_devtools.toml")
    if not config_path.is_file():
        if path is not None:
            raise FileNotFoundError(
                f"Agent DevTools config does not exist: {config_path}"
            )
        return None
    return AgentDevToolsConfig.from_file(config_path)


def _export_bundle_if_requested(
    report_path: Path,
    requested: bool,
    *,
    redact: bool = False,
) -> bool:
    if not requested:
        return True
    try:
        bundle_path = export_diagnostic_bundle(
            report_path.parent,
            redact=redact,
        )
    except (BundleExportError, OSError, ValueError) as error:
        print(f"Bundle export failed: {type(error).__name__}: {error}")
        return False
    print(f"Bundle: {bundle_path.resolve()}")
    return True


def _update_run_index(report_path: Path, *, open_index: bool) -> Path | None:
    try:
        index_path = write_run_index(report_path.parent.parent)
    except (OSError, ValueError, TypeError) as error:
        print(f"Run index could not be created: {type(error).__name__}")
        return None

    print(f"Run index: {index_path.resolve()}")
    if open_index:
        try:
            open_local_report(index_path)
        except Exception as error:
            print(f"Run index could not be opened: {type(error).__name__}")
    return index_path


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
    require_recorded_actions: bool = False,
) -> SummaryStatus:
    if run_error is not None:
        return "errored"
    if session is None or session.verification is None:
        return "unverified"
    if (
        require_recorded_actions
        and session.action_count == 0
        and session.verification.passed
    ):
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
    run_issue = classify_run_issue(session) if session is not None else None
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
        "issue_code": run_issue.code.value if run_issue is not None else None,
        "issue_title": run_issue.title if run_issue is not None else None,
        "issue_next_step": (
            run_issue.next_step if run_issue is not None else None
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


def _evaluation_summary_status(evaluation: AgentEvaluation) -> SummaryStatus:
    if evaluation.all_runs_passed:
        return "passed"
    if evaluation.errored_count:
        return "errored"
    if evaluation.failed_count:
        return "failed"
    return "unverified"


def _build_evaluation_summary(
    evaluation: AgentEvaluation,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "evaluation",
        "status": _evaluation_summary_status(evaluation),
        "task": evaluation.task,
        "requested_run_count": evaluation.requested_run_count,
        "attempted_run_count": evaluation.attempted_run_count,
        "passed_count": evaluation.passed_count,
        "failed_count": evaluation.failed_count,
        "unverified_count": evaluation.unverified_count,
        "errored_count": evaluation.errored_count,
        "issue_code_counts": evaluation.issue_code_counts,
        "empirical_pass_rate": evaluation.empirical_pass_rate,
        "report_path": _summary_path(evaluation.report_path),
        "evaluation_path": _summary_path(
            evaluation.output_dir / "evaluation.json"
        ),
        "comparison_path": _summary_path(
            evaluation.comparison_report_path
        ),
    }


def _write_evaluation_summary(
    path: Path | None,
    evaluation: AgentEvaluation,
) -> None:
    if path is None:
        return
    _write_json(_build_evaluation_summary(evaluation), path)
    print(f"Summary: {path.resolve()}")


def _print_evaluation_summary(evaluation: AgentEvaluation) -> None:
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
    print(
        "Evaluation: "
        f"{(evaluation.output_dir / 'evaluation.json').resolve()}"
    )
    print(f"Report: {evaluation.report_path.resolve()}")
    if evaluation.comparison_report_path is not None:
        print(f"Comparison: {evaluation.comparison_report_path.resolve()}")


def _compact_output(value: str, *, limit: int = 160) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _format_preflight(result: BrowserUsePreflightResult) -> str:
    lines = ["Agent DevTools preflight"]
    lines.append(f"Result: {'PASS' if result.passed else 'FAIL'}")
    for check in result.checks:
        status = "PASS" if check.passed else "FAIL"
        lines.append(f"[{status}] {check.name}: {check.detail}")
    return "\n".join(lines)


def _format_run_summary(
    session: ActionSession | None,
    report_path: Path,
    *,
    run_error: BaseException | None = None,
    require_recorded_actions: bool = False,
) -> str:
    actions = session.actions if session is not None else []
    action_failures = sum(
        action.status is ActionStatus.FAILURE for action in actions
    )
    action_successes = len(actions) - action_failures
    verification = session.verification if session is not None else None
    run_issue = classify_run_issue(session) if session is not None else None
    coverage_unverified = (
        require_recorded_actions
        and not actions
        and (verification is None or verification.passed)
    )

    if run_error is not None:
        result = "ERROR"
    elif coverage_unverified:
        result = "UNVERIFIED"
    elif verification is None:
        result = "UNVERIFIED"
    elif verification.passed:
        result = "PASS"
    else:
        result = "FAIL"

    lines = ["Agent DevTools"]
    if session is not None and session.goal is not None:
        lines.append(f"Task: {_compact_output(session.goal)}")
    lines.extend(
        (
            f"Result: {result}",
            f"Actions: {action_successes} succeeded, {action_failures} failed",
            (
                "Final check: not run"
                if verification is None
                else f"Final check: {'passed' if verification.passed else 'failed'}"
            ),
        )
    )

    if run_error is not None:
        lines.append(f"Reason: agent run failed ({type(run_error).__name__})")
    elif coverage_unverified:
        lines.append(
            "Reason: no browser actions captured "
            "(strict recording coverage is enabled)"
        )
    elif verification is not None and not verification.passed:
        reason = verification.failure_reason
        if reason:
            lines.append(f"Reason: {_compact_output(reason)}")
    elif verification is None and run_issue is not None:
        lines.append(f"Issue: {run_issue.title}")
        lines.append(f"Next: {run_issue.next_step}")
    elif (
        verification is None
        and session is not None
        and session.verification_note is not None
    ):
        lines.append(f"Reason: {_compact_output(session.verification_note)}")

    lines.append(f"Report: {report_path.resolve()}")
    return "\n".join(lines)


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

    if args.preflight and args.runs != 1:
        print("Configuration error: --preflight cannot be combined with --runs")
        return 2
    if args.preflight and args.export_bundle:
        print("Configuration error: --export-bundle requires a completed task")
        return 2
    if args.redact and not args.export_bundle:
        print("Configuration error: --redact requires --export-bundle")
        return 2
    if args.preflight and args.open_index:
        print("Configuration error: --open-index requires a completed task")
        return 2

    try:
        browser_kwargs = _browser_kwargs(config, headed=args.headed)
    except (OSError, ValueError) as error:
        print(f"Configuration error: {error}")
        _write_errored_summary(args.summary_json, type(error).__name__)
        return 2

    if args.runs > 1:
        evaluation_config = config
        if args.open_report and not (
            evaluation_config is not None and evaluation_config.open_report
        ):
            evaluation_config = replace(
                evaluation_config or AgentDevToolsConfig(),
                open_report=True,
            )

        def create_agent(agent_task: str) -> object:
            return Agent(
                task=agent_task,
                llm=llm,
                browser=Browser(**browser_kwargs),
                use_judge=True,
            )

        try:
            evaluation = await evaluate_browser_use_agent(
                agent_factory=create_agent,
                task=task,
                runs=args.runs,
                max_steps=args.max_steps,
                config=evaluation_config,
            )
        except Exception as error:
            print(f"Evaluation error: {type(error).__name__}: {error}")
            _write_errored_summary(
                args.summary_json,
                type(error).__name__,
            )
            return 2

        _print_evaluation_summary(evaluation)
        _write_evaluation_summary(args.summary_json, evaluation)
        bundle_ok = _export_bundle_if_requested(
            evaluation.report_path,
            args.export_bundle,
            redact=args.redact,
        )
        _update_run_index(
            evaluation.report_path,
            open_index=args.open_index,
        )
        return 0 if bundle_ok and evaluation.all_runs_passed else 1

    try:
        browser = Browser(**browser_kwargs)
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
    show_summary = config is None or config.terminal_summary
    require_recorded_actions = (
        config is not None and config.require_recorded_actions
    )
    try:
        agent = observe_browser_use_agent(
            raw_agent,
            config=config,
            print_summary=False,
        )
    except (OSError, TypeError, ValueError) as error:
        await browser.stop()
        print(f"Preflight: FAIL ({type(error).__name__})")
        print(f"Reason: {error}")
        return 1

    if args.preflight:
        result = agent.preflight()
        print(_format_preflight(result))
        await browser.stop()
        return 0 if result.passed else 1

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

    bundle_ok = _export_bundle_if_requested(
        report_path,
        args.export_bundle,
        redact=args.redact,
    )
    _update_run_index(report_path, open_index=args.open_index)

    if run_error is not None:
        if show_summary:
            print(
                _format_run_summary(
                    agent.last_session,
                    report_path,
                    run_error=run_error,
                )
            )
        _write_errored_summary(
            args.summary_json,
            type(run_error).__name__,
            report_path=report_path,
            session=agent.last_session,
        )
        return 1

    try:
        agent.assert_last_task_passed()
    except AssertionError:
        result_is_verified = False
    else:
        result_is_verified = True

    if show_summary:
        print(
            _format_run_summary(
                agent.last_session,
                report_path,
                require_recorded_actions=require_recorded_actions,
            )
        )

    _write_summary(
        args.summary_json,
        status=_summary_status(
            agent.last_session,
            require_recorded_actions=require_recorded_actions,
        ),
        report_path=report_path,
        session=agent.last_session,
    )

    if args.open_report and not (config is not None and config.open_report):
        try:
            agent.open_last_report()
        except Exception as error:
            print(f"Report could not be opened: {type(error).__name__}")

    return 0 if result_is_verified and bundle_ok else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the installed Agent DevTools command-line workflow."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "dashboard":
        return _control_center_main(arguments[1:])
    return asyncio.run(_browser_use_main(arguments))


__all__ = ["main"]
