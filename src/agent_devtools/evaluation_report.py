from __future__ import annotations

from html import escape
from pathlib import Path

from agent_devtools.evaluation import (
    AgentEvaluation,
    EvaluationRun,
    EvaluationRunStatus,
)


_STATUS_LABELS = {
    EvaluationRunStatus.PASSED: "Passed",
    EvaluationRunStatus.FAILED: "Failed",
    EvaluationRunStatus.UNVERIFIED: "Unverified",
    EvaluationRunStatus.ERRORED: "Errored",
}


def render_evaluation_html(evaluation: AgentEvaluation) -> str:
    representative = evaluation.representative_success_run_number
    baseline_html = (
        '<a href="runs/{0:03d}/report.html">Run {0}</a>'.format(
            representative
        )
        if representative is not None
        else "No successful baseline was available. Divergences are grouped "
        "only from signals within each unsuccessful run."
    )
    repeated_patterns = [
        pattern for pattern in evaluation.failure_patterns if pattern.repeated
    ]
    pattern_html = "".join(
        f"""
        <article class="pattern">
          <div><strong>{escape(pattern.summary)}</strong></div>
          <div class="muted">Runs {', '.join(map(str, pattern.run_numbers))}</div>
          <a href="runs/{pattern.representative_run_number:03d}/report.html">
            Inspect representative run {pattern.representative_run_number}
          </a>
        </article>
        """
        for pattern in repeated_patterns
    ) or '<p class="muted">No repeated unsuccessful pattern was observed.</p>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent stability evaluation</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui,
      -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f4f7fb; color: #172033; }}
    main {{ width: min(1120px, calc(100% - 32px)); margin: 32px auto 64px; }}
    section {{ background: #fff; border: 1px solid #dfe6f0; border-radius: 16px;
      box-shadow: 0 12px 32px rgba(31, 50, 81, .07); margin-bottom: 20px;
      padding: 24px; }}
    h1, h2 {{ margin: 0 0 14px; letter-spacing: -.02em; }}
    h1 {{ font-size: 2rem; }} h2 {{ font-size: 1.2rem; }}
    .eyebrow {{ color: #42658f; font-size: .76rem; font-weight: 800;
      letter-spacing: .08em; text-transform: uppercase; }}
    .task {{ font-size: 1.08rem; line-height: 1.55; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px; margin-top: 20px; }}
    .metric {{ background: #f7f9fc; border: 1px solid #e2e8f2;
      border-radius: 12px; padding: 14px; }}
    .metric span {{ color: #64748b; display: block; font-size: .76rem;
      font-weight: 700; margin-bottom: 5px; text-transform: uppercase; }}
    .metric strong {{ font-size: 1.25rem; }}
    .counts {{ display: flex; flex-wrap: wrap; gap: 9px; margin-top: 16px; }}
    .pill {{ border-radius: 999px; font-size: .83rem; font-weight: 700;
      padding: 7px 11px; }}
    .passed {{ background: #dcfce7; color: #166534; }}
    .failed {{ background: #fee2e2; color: #991b1b; }}
    .unverified {{ background: #fef3c7; color: #92400e; }}
    .errored {{ background: #ede9fe; color: #5b21b6; }}
    .baseline {{ border-left: 4px solid #2563eb; background: #eff6ff;
      border-radius: 8px; margin-top: 20px; padding: 14px 16px; }}
    .pattern {{ border: 1px solid #fecaca; border-left: 4px solid #dc2626;
      border-radius: 10px; margin-top: 12px; padding: 14px 16px; }}
    .muted {{ color: #64748b; }} a {{ color: #1459b8; font-weight: 650; }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #e4e9f1; padding: 13px 10px;
      text-align: left; vertical-align: top; }}
    th {{ color: #53627a; font-size: .76rem; letter-spacing: .04em;
      text-transform: uppercase; }}
    td {{ font-size: .9rem; }}
    .divergence {{ min-width: 280px; line-height: 1.4; }}
    .note {{ color: #64748b; font-size: .84rem; margin-top: 16px; }}
    @media (max-width: 760px) {{ .metrics {{ grid-template-columns: 1fr 1fr; }} }}
  </style>
</head>
<body>
<main>
  <section>
    <div class="eyebrow">Agent DevTools · evaluation schema 1</div>
    <h1>Stability evaluation</h1>
    <p class="task"><strong>Task:</strong> {escape(evaluation.task)}</p>
    <div class="metrics">
      {_metric("Requested runs", str(evaluation.requested_run_count))}
      {_metric("Completed runs", str(evaluation.completed_run_count))}
      {_metric("Empirical pass rate", _percent(evaluation.empirical_pass_rate))}
      {_metric("Average duration", _milliseconds(evaluation.average_duration_ms))}
      {_metric("Median duration", _milliseconds(evaluation.median_duration_ms))}
      {_metric("Average actions", _number(evaluation.average_action_count))}
      {_metric("Median actions", _number(evaluation.median_action_count))}
    </div>
    <div class="counts">
      {_pill("passed", evaluation.passed_count)}
      {_pill("failed", evaluation.failed_count)}
      {_pill("unverified", evaluation.unverified_count)}
      {_pill("errored", evaluation.errored_count)}
    </div>
    <div class="baseline"><strong>Representative successful run:</strong>
      {baseline_html}
    </div>
    <p class="note">The empirical pass rate describes these observed attempts.
      A small sample does not prove the agent's true reliability.</p>
  </section>
  <section>
    <h2>Repeated unsuccessful patterns</h2>
    {pattern_html}
  </section>
  <section>
    <h2>All runs</h2>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Run</th><th>Result</th><th>Duration</th>
          <th>Actions</th><th>First observed divergence</th><th>Trace</th></tr></thead>
        <tbody>{''.join(_run_row(run) for run in evaluation.runs)}</tbody>
      </table>
    </div>
  </section>
</main>
</body>
</html>
"""


def write_evaluation_html(
    evaluation: AgentEvaluation,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_evaluation_html(evaluation)
    normalized = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
    output_path.write_text(normalized, encoding="utf-8")


def _metric(label: str, value: str) -> str:
    return (
        f'<div class="metric"><span>{escape(label)}</span>'
        f'<strong>{escape(value)}</strong></div>'
    )


def _pill(status: str, count: int) -> str:
    return f'<span class="pill {status}">{status.title()}: {count}</span>'


def _run_row(run: EvaluationRun) -> str:
    divergence = run.divergence.summary if run.divergence is not None else "—"
    if run.status is EvaluationRunStatus.ERRORED:
        divergence = f"Errored during {run.error_phase} ({run.error_type})."
    return f"""
      <tr>
        <td><strong>{run.run_number}</strong></td>
        <td><span class="pill {run.status.value}">{_STATUS_LABELS[run.status]}</span></td>
        <td>{run.duration_ms} ms</td>
        <td>{run.action_count}</td>
        <td class="divergence">{escape(divergence)}</td>
        <td><a href="{escape(run.report_path.as_posix())}">Open report</a></td>
      </tr>
    """


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _milliseconds(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f} ms"


def _number(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}"


__all__ = ["render_evaluation_html", "write_evaluation_html"]
