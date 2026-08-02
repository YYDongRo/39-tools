from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path

from agent_devtools import ActionRecord, ActionSession, ActionStatus
from agent_devtools.evaluation import AgentEvaluation, EvaluationRun, EvaluationRunStatus
from agent_devtools.evaluation_analysis import analyze_evaluation_runs
from agent_devtools.evaluation_report import write_evaluation_html
from agent_devtools.evaluation_serialization import write_evaluation_json
from agent_devtools.report import write_session_html
from agent_devtools.serialization import write_session_json
from agent_devtools.verification import VerificationResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "sample-evaluation"
TASK = "Find the wireless headphones and open the correct product page."
SHOP_ROOT = "https://shop.example.test"
EVALUATION_ID = "20260801T170000000000Z-sample01"
STARTED_AT = datetime(2026, 8, 1, 17, 0, tzinfo=UTC)


def _action(
    *,
    run_started_at: datetime,
    action_number: int,
    action_type: str,
    arguments: dict[str, object],
    before_url: str,
    after_url: str,
) -> ActionRecord:
    action_dir = Path("actions") / f"{action_number:03d}"
    return ActionRecord(
        action_type=action_type,
        arguments=arguments,
        start_time=run_started_at + timedelta(seconds=action_number),
        duration_ms=80 + action_number * 17,
        status=ActionStatus.SUCCESS,
        screenshot_before=action_dir / "before.svg",
        screenshot_after=action_dir / "after.svg",
        observations={
            "page_url_before": before_url,
            "page_url_after": after_url,
            "state_before": {"url": before_url, "title": "Example Shop"},
            "state_after": {"url": after_url, "title": "Example Shop"},
        },
    )


def _session(
    run_number: int,
    result: str,
) -> tuple[ActionSession, datetime, datetime, int]:
    run_started_at = STARTED_AT + timedelta(minutes=run_number)
    search_url = f"{SHOP_ROOT}/search?q=wireless-headphones"
    actions = [
        _action(
            run_started_at=run_started_at,
            action_number=1,
            action_type="navigate",
            arguments={"url": f"{SHOP_ROOT}/"},
            before_url="about:blank",
            after_url=f"{SHOP_ROOT}/",
        ),
        _action(
            run_started_at=run_started_at,
            action_number=2,
            action_type="fill",
            arguments={
                "selector": "#product-search",
                "text": "Wireless Headphones",
            },
            before_url=f"{SHOP_ROOT}/",
            after_url=search_url,
        ),
    ]
    if result != "unverified":
        correct = result == "passed"
        product = "wireless-headphones" if correct else "usb-c-cable"
        actions.append(
            _action(
                run_started_at=run_started_at,
                action_number=3,
                action_type="click",
                arguments={
                    "selector": (
                        "#wireless-headphones" if correct else "#usb-c-cable"
                    )
                },
                before_url=search_url,
                after_url=f"{SHOP_ROOT}/products/{product}",
            )
        )

    verification: VerificationResult | None = None
    verification_note: str | None = None
    if result == "passed":
        verification = VerificationResult(
            expected_state="the Wireless Headphones product page is open",
            observed_state="the Wireless Headphones product page is open",
            passed=True,
            evidence={"final_url": f"{SHOP_ROOT}/products/wireless-headphones"},
        )
    elif result == "failed":
        verification = VerificationResult(
            expected_state="the Wireless Headphones product page is open",
            observed_state="the USB-C Cable product page is open",
            passed=False,
            failure_reason="The agent selected the wrong product result.",
            evidence={"final_url": f"{SHOP_ROOT}/products/usb-c-cable"},
        )
    else:
        verification_note = "The run ended before a final task judgment."

    duration_ms = 900 + run_number * 110
    run_ended_at = run_started_at + timedelta(milliseconds=duration_ms)
    return (
        ActionSession(
            actions=actions,
            goal=TASK,
            verification_source="deterministic sample judge",
            verification_note=verification_note,
            verification=verification,
        ),
        run_started_at,
        run_ended_at,
        duration_ms,
    )


def build_sample_evaluation(
    output_dir: Path,
) -> tuple[AgentEvaluation, dict[int, ActionSession]]:
    results = ("passed", "failed", "passed", "unverified", "failed", "passed")
    sessions: dict[int, ActionSession] = {}
    runs: list[EvaluationRun] = []
    for run_number, result in enumerate(results, start=1):
        session, run_started_at, run_ended_at, duration_ms = _session(
            run_number,
            result,
        )
        sessions[run_number] = session
        status = {
            "passed": EvaluationRunStatus.PASSED,
            "failed": EvaluationRunStatus.FAILED,
            "unverified": EvaluationRunStatus.UNVERIFIED,
        }[result]
        relative_trace = Path("runs") / f"{run_number:03d}"
        runs.append(
            EvaluationRun(
                run_number=run_number,
                status=status,
                started_at=run_started_at,
                ended_at=run_ended_at,
                duration_ms=duration_ms,
                action_count=session.action_count,
                trace_directory=relative_trace,
                report_path=relative_trace / "report.html",
            )
        )

    analyzed_runs, representative, patterns = analyze_evaluation_runs(
        tuple(runs),
        sessions,
    )
    return (
        AgentEvaluation(
            evaluation_id=EVALUATION_ID,
            task=TASK,
            started_at=STARTED_AT,
            ended_at=STARTED_AT + timedelta(minutes=7),
            requested_run_count=len(results),
            runs=analyzed_runs,
            output_dir=output_dir,
            representative_success_run_number=representative,
            failure_patterns=patterns,
        ),
        sessions,
    )


def _snapshot(url: str, label: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">
  <rect width="960" height="540" fill="#f4f7fb"/>
  <rect x="35" y="35" width="890" height="470" rx="18" fill="#fff" stroke="#cad5e3" stroke-width="2"/>
  <rect x="35" y="35" width="890" height="58" rx="18" fill="#e5eaf1"/>
  <rect x="120" y="52" width="760" height="27" rx="7" fill="#fff"/>
  <text x="140" y="71" font-family="Arial, sans-serif" font-size="14" fill="#475569">{escape(url)}</text>
  <text x="90" y="180" font-family="Arial, sans-serif" font-size="34" font-weight="700" fill="#172033">Example Shop</text>
  <text x="90" y="225" font-family="Arial, sans-serif" font-size="22" fill="#52657e">{escape(label)}</text>
  <rect x="90" y="285" width="780" height="120" rx="12" fill="#eef3f9"/>
  <rect x="120" y="320" width="360" height="18" rx="5" fill="#c7d2e0"/>
  <rect x="120" y="356" width="610" height="14" rx="5" fill="#d9e1ec"/>
</svg>
"""


def _write_session_trace(
    output_dir: Path,
    run_number: int,
    session: ActionSession,
) -> list[Path]:
    trace_dir = output_dir / "runs" / f"{run_number:03d}"
    generated: list[Path] = []
    for action_number, action in enumerate(session.actions, start=1):
        before = trace_dir / action.screenshot_before  # type: ignore[operator]
        after = trace_dir / action.screenshot_after  # type: ignore[operator]
        before.parent.mkdir(parents=True, exist_ok=True)
        before.write_text(
            _snapshot(
                str(action.observations["page_url_before"]),
                f"Before action {action_number}: {action.action_type}",
            ),
            encoding="utf-8",
        )
        after.write_text(
            _snapshot(
                str(action.observations["page_url_after"]),
                f"After action {action_number}: {action.action_type}",
            ),
            encoding="utf-8",
        )
        generated.extend((before, after))
    session_path = trace_dir / "session.json"
    report_path = trace_dir / "report.html"
    write_session_json(session, session_path)
    write_session_html(session, report_path)
    _normalize_text_file(report_path)
    generated.extend((session_path, report_path))
    return generated


def generate_sample_evaluation(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> list[Path]:
    evaluation, sessions = build_sample_evaluation(output_dir)
    generated: list[Path] = []
    for run_number, session in sessions.items():
        generated.extend(_write_session_trace(output_dir, run_number, session))
    json_path = output_dir / "evaluation.json"
    report_path = output_dir / "report.html"
    write_evaluation_json(evaluation, json_path)
    write_evaluation_html(evaluation, report_path)
    generated.extend((json_path, report_path))
    return generated


def _normalize_text_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    normalized = "\n".join(line.rstrip() for line in text.splitlines()) + "\n"
    path.write_text(normalized, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the sanitized Agent DevTools stability sample."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="output directory (default: docs/sample-evaluation)",
    )
    args = parser.parse_args()
    generated = generate_sample_evaluation(args.output)
    print(f"Generated {len(generated)} files in {args.output}")


if __name__ == "__main__":
    main()
