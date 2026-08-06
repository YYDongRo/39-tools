"""Static HTML report for comparing two evaluation runs."""

from __future__ import annotations

from html import escape
from pathlib import Path

from agent_devtools.evaluation import (
    EvaluationComparison,
    EvaluationComparisonStatus,
    FailurePattern,
)


def render_evaluation_comparison_html(
    comparison: EvaluationComparison,
    *,
    baseline_report_href: str | None = None,
    current_report_href: str | None = "report.html",
) -> str:
    links = []
    if baseline_report_href is not None:
        links.append(
            f'<a href="{escape(baseline_report_href, quote=True)}">'
            "Open previous report</a>"
        )
    if current_report_href is not None:
        links.append(
            f'<a href="{escape(current_report_href, quote=True)}">'
            "Open current report</a>"
        )
    links_html = (
        '<nav class="links">' + " · ".join(links) + "</nav>"
        if links
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent DevTools evaluation comparison</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui,
      -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f4f7fb; color: #172033; }}
    main {{ width: min(960px, calc(100% - 32px)); margin: 32px auto 64px; }}
    section {{ background: #fff; border: 1px solid #dfe6f0; border-radius: 16px;
      box-shadow: 0 12px 32px rgba(31, 50, 81, .07); margin-bottom: 20px;
      padding: 24px; }}
    h1, h2 {{ margin: 0 0 14px; letter-spacing: -.02em; }}
    h1 {{ font-size: 2rem; }} h2 {{ font-size: 1.2rem; }}
    .eyebrow {{ color: #42658f; font-size: .76rem; font-weight: 800;
      letter-spacing: .08em; text-transform: uppercase; }}
    .task {{ font-size: 1.08rem; line-height: 1.55; }}
    .verdict {{ border-radius: 12px; display: inline-block; font-weight: 800;
      margin: 4px 0 18px; padding: 9px 14px; }}
    .improved {{ background: #dcfce7; color: #166534; }}
    .unchanged {{ background: #e2e8f0; color: #334155; }}
    .regressed {{ background: #fee2e2; color: #991b1b; }}
    .incomparable {{ background: #fef3c7; color: #92400e; }}
    .metrics {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #e4e9f1; padding: 12px 10px;
      text-align: left; vertical-align: top; }}
    th {{ color: #53627a; font-size: .76rem; letter-spacing: .04em;
      text-transform: uppercase; }}
    td {{ font-size: .92rem; }}
    .delta-positive {{ color: #166534; font-weight: 700; }}
    .delta-negative {{ color: #991b1b; font-weight: 700; }}
    .pattern {{ border-radius: 10px; margin-top: 12px; padding: 14px 16px; }}
    .pattern-new {{ background: #fff1f2; border: 1px solid #fecaca;
      border-left: 4px solid #dc2626; }}
    .pattern-resolved {{ background: #f0fdf4; border: 1px solid #bbf7d0;
      border-left: 4px solid #16a34a; }}
    .muted {{ color: #64748b; }}
    .links {{ margin-top: 18px; }}
    a {{ color: #1459b8; font-weight: 650; }}
    .empty {{ color: #64748b; margin: 0; }}
  </style>
</head>
<body>
<main>
  <section>
    <div class="eyebrow">Agent DevTools · comparison schema 1</div>
    <h1>Evaluation comparison</h1>
    <div class="verdict {comparison.status.value}">
      {escape(comparison.status.value.title())}
    </div>
    <p class="task"><strong>Task:</strong> {escape(comparison.task)}</p>
    <p>{escape(comparison.summary)}</p>
    {f'<p class="muted">{escape(comparison.reason)}</p>' if comparison.reason else ''}
    {links_html}
  </section>
  <section>
    <h2>What changed</h2>
    <table class="metrics">
      <thead><tr><th>Metric</th><th>Previous</th><th>Current</th><th>Change</th></tr></thead>
      <tbody>
        {_metric_row("Pass rate", _percent(comparison.baseline_pass_rate), _percent(comparison.current_pass_rate), _percent_delta(comparison.pass_rate_delta))}
        {_metric_row("Passed runs", str(comparison.baseline_counts.passed), str(comparison.current_counts.passed), _integer_delta(comparison.current_counts.passed - comparison.baseline_counts.passed))}
        {_metric_row("Failed runs", str(comparison.baseline_counts.failed), str(comparison.current_counts.failed), _integer_delta(comparison.current_counts.failed - comparison.baseline_counts.failed))}
        {_metric_row("Unverified runs", str(comparison.baseline_counts.unverified), str(comparison.current_counts.unverified), _integer_delta(comparison.current_counts.unverified - comparison.baseline_counts.unverified))}
        {_metric_row("Errored runs", str(comparison.baseline_counts.errored), str(comparison.current_counts.errored), _integer_delta(comparison.current_counts.errored - comparison.baseline_counts.errored))}
        {_metric_row("Average duration", _milliseconds(comparison.baseline_average_duration_ms), _milliseconds(comparison.current_average_duration_ms), _metric_delta(comparison.baseline_average_duration_ms, comparison.current_average_duration_ms, " ms"))}
        {_metric_row("Average actions", _number(comparison.baseline_average_action_count), _number(comparison.current_average_action_count), _metric_delta(comparison.baseline_average_action_count, comparison.current_average_action_count, ""))}
      </tbody>
    </table>
  </section>
  <section>
    <h2>New failure patterns</h2>
    {_patterns_html(comparison.new_patterns, "pattern-new", "No new failure pattern was observed.")}
  </section>
  <section>
    <h2>Resolved failure patterns</h2>
    {_patterns_html(comparison.resolved_patterns, "pattern-resolved", "No previous failure pattern disappeared.")}
  </section>
</main>
</body>
</html>
"""


def write_evaluation_comparison_html(
    comparison: EvaluationComparison,
    output_path: Path,
    *,
    baseline_report_href: str | None = None,
    current_report_href: str | None = "report.html",
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_evaluation_comparison_html(
        comparison,
        baseline_report_href=baseline_report_href,
        current_report_href=current_report_href,
    )
    normalized = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        output_file.write(normalized)


def _patterns_html(
    patterns: tuple[FailurePattern, ...],
    class_name: str,
    empty_text: str,
) -> str:
    if not patterns:
        return f'<p class="empty">{escape(empty_text)}</p>'
    return "".join(
        f'<article class="pattern {class_name}">'
        f"<strong>{escape(pattern.summary)}</strong>"
        f'<div class="muted">Runs: {", ".join(map(str, pattern.run_numbers))}</div>'
        "</article>"
        for pattern in patterns
    )


def _metric_row(label: str, baseline: str, current: str, delta: str) -> str:
    return (
        f"<tr><td><strong>{escape(label)}</strong></td>"
        f"<td>{escape(baseline)}</td><td>{escape(current)}</td>"
        f"<td>{escape(delta)}</td></tr>"
    )


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _percent_delta(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.1f} percentage points"


def _integer_delta(value: int) -> str:
    return f"{value:+d}"


def _milliseconds(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f} ms"


def _number(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}"


def _metric_delta(
    baseline: float | None,
    current: float | None,
    suffix: str,
) -> str:
    if baseline is None or current is None:
        return "—"
    delta = current - baseline
    return f"{delta:+.1f}{suffix}"


__all__ = [
    "render_evaluation_comparison_html",
    "write_evaluation_comparison_html",
]
