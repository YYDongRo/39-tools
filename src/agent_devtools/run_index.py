"""A small local index for finding generated Agent DevTools reports."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from tempfile import NamedTemporaryFile

from agent_devtools.evaluation_serialization import read_evaluation_json
from agent_devtools.serialization import read_session_json
from agent_devtools.session import ActionSession


@dataclass(frozen=True)
class _RunIndexEntry:
    kind: str
    status: str
    task: str
    timestamp: datetime
    duration: str
    actions: str
    detail: str
    report_href: str


_STATUS_LABELS = {
    "passed": "Passed",
    "failed": "Failed",
    "unverified": "Unverified",
    "attention": "Needs attention",
}


def write_run_index(root: str | Path) -> Path:
    """Write and return a static index for reports below ``root``.

    The index only links to files using relative POSIX paths. Incomplete or
    unreadable run directories remain visible with a diagnostic row rather
    than preventing the other reports from being listed.
    """

    output_root = Path(root)
    if output_root.exists() and not output_root.is_dir():
        raise ValueError(f"run index root is not a directory: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    entries = _discover_entries(output_root)
    bundles = _discover_bundles(output_root)
    output_path = output_root / "index.html"
    _write_html(output_path, _render_index(entries, bundles))
    return output_path


def _discover_entries(root: Path) -> list[_RunIndexEntry]:
    entries: list[_RunIndexEntry] = []
    for candidate in root.iterdir():
        if not candidate.is_dir() or not (candidate / "report.html").is_file():
            continue
        report_href = _relative_href(candidate / "report.html", root)
        evaluation_path = candidate / "evaluation.json"
        session_path = candidate / "session.json"
        if evaluation_path.is_file():
            entries.append(
                _evaluation_entry(
                    evaluation_path,
                    report_href,
                    candidate / "report.html",
                )
            )
        elif session_path.is_file():
            entries.append(
                _session_entry(
                    session_path,
                    report_href,
                    candidate / "report.html",
                )
            )
        else:
            entries.append(
                _unreadable_entry(
                    report_href,
                    candidate / "report.html",
                    "session.json or evaluation.json is missing",
                )
            )

    entries.sort(
        key=lambda entry: (entry.timestamp, entry.report_href),
        reverse=True,
    )
    return entries


def _session_entry(
    session_path: Path,
    report_href: str,
    report_path: Path,
) -> _RunIndexEntry:
    try:
        session = read_session_json(session_path)
    except (OSError, ValueError, TypeError) as error:
        return _unreadable_entry(
            report_href,
            report_path,
            f"session could not be read ({type(error).__name__})",
        )

    verification = session.verification
    if verification is None:
        status = "unverified"
        detail = (
            session.verification_note
            or session.issue_code
            or "Final task verification was not available"
        )
    elif verification.passed:
        status = "passed"
        detail = "Final task check passed"
    else:
        status = "failed"
        detail = verification.failure_reason or "Final task check failed"

    failed_actions = sum(
        action.outcome.value == "failure" for action in session.actions
    )
    if failed_actions and status == "passed":
        detail += f"; {failed_actions} action failure(s)"

    timestamp = (
        session.actions[0].start_time
        if session.actions
        else _report_timestamp(report_path)
    )
    return _RunIndexEntry(
        kind="Task run",
        status=status,
        task=_display_text(session.goal or "Task unavailable"),
        timestamp=timestamp,
        duration=f"{sum(action.duration_ms for action in session.actions)} ms",
        actions=str(session.action_count),
        detail=_display_text(detail),
        report_href=report_href,
    )


def _evaluation_entry(
    evaluation_path: Path,
    report_href: str,
    report_path: Path,
) -> _RunIndexEntry:
    try:
        evaluation = read_evaluation_json(evaluation_path)
    except (OSError, ValueError, TypeError) as error:
        return _unreadable_entry(
            report_href,
            report_path,
            f"evaluation could not be read ({type(error).__name__})",
        )

    status = "passed" if evaluation.all_runs_passed else "attention"
    detail = (
        f"{evaluation.passed_count} passed, {evaluation.failed_count} failed, "
        f"{evaluation.unverified_count} unverified, "
        f"{evaluation.errored_count} errored"
    )
    duration = int(
        max(0, (evaluation.ended_at - evaluation.started_at).total_seconds() * 1000)
    )
    return _RunIndexEntry(
        kind="Stability evaluation",
        status=status,
        task=_display_text(evaluation.task),
        timestamp=evaluation.started_at,
        duration=f"{duration} ms",
        actions=(
            "—"
            if evaluation.average_action_count is None
            else f"avg {evaluation.average_action_count:.1f}"
        ),
        detail=_display_text(detail),
        report_href=report_href,
    )


def _unreadable_entry(
    report_href: str,
    report_path: Path,
    detail: str,
) -> _RunIndexEntry:
    return _RunIndexEntry(
        kind="Report",
        status="unverified",
        task="Metadata unavailable",
        timestamp=_report_timestamp(report_path),
        duration="—",
        actions="—",
        detail=detail,
        report_href=report_href,
    )


def _discover_bundles(root: Path) -> list[tuple[str, str]]:
    bundle_root = root / "bundles"
    if not bundle_root.is_dir():
        return []
    bundles: list[tuple[str, str]] = []
    for path in sorted(bundle_root.glob("*.zip"), key=lambda item: item.name):
        bundles.append((path.name, _relative_href(path, root)))
    return list(reversed(bundles))


def _relative_href(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _report_timestamp(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _display_text(value: str, limit: int = 180) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _render_index(
    entries: list[_RunIndexEntry],
    bundles: list[tuple[str, str]],
) -> str:
    counts = {
        status: sum(entry.status == status for entry in entries)
        for status in ("passed", "failed", "unverified", "attention")
    }
    if entries:
        rows = "".join(_entry_row(entry) for entry in entries)
    else:
        rows = '<tr><td colspan="7" class="muted">No completed reports yet.</td></tr>'

    if bundles:
        bundle_html = "".join(
            f'<li><a href="{escape(href, quote=True)}">{escape(name)}</a></li>'
            for name, href in bundles
        )
    else:
        bundle_html = '<li class="muted">No exported bundles yet.</li>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent DevTools run index</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui,
      -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f4f7fb; color: #172033; }}
    main {{ width: min(1180px, calc(100% - 32px)); margin: 32px auto 64px; }}
    section {{ background: #fff; border: 1px solid #dfe6f0; border-radius: 16px;
      box-shadow: 0 12px 32px rgba(31, 50, 81, .07); margin-bottom: 20px;
      padding: 24px; }}
    h1, h2 {{ margin: 0 0 14px; letter-spacing: -.02em; }}
    h1 {{ font-size: 2rem; }} h2 {{ font-size: 1.2rem; }}
    .eyebrow {{ color: #42658f; font-size: .76rem; font-weight: 800;
      letter-spacing: .08em; text-transform: uppercase; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px; margin-top: 20px; }}
    .metric {{ background: #f7f9fc; border: 1px solid #e2e8f2;
      border-radius: 12px; padding: 14px; }}
    .metric span {{ color: #64748b; display: block; font-size: .76rem;
      font-weight: 700; margin-bottom: 5px; text-transform: uppercase; }}
    .metric strong {{ font-size: 1.25rem; }}
    .muted {{ color: #64748b; }}
    .table-wrap {{ overflow-x: auto; }} table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #e4e9f1; padding: 13px 10px;
      text-align: left; vertical-align: top; }}
    th {{ color: #53627a; font-size: .76rem; letter-spacing: .04em;
      text-transform: uppercase; }} td {{ font-size: .9rem; }}
    .task {{ min-width: 260px; line-height: 1.4; }}
    .detail {{ min-width: 220px; line-height: 1.4; }}
    .pill {{ border-radius: 999px; display: inline-block; font-size: .8rem;
      font-weight: 700; padding: 6px 9px; white-space: nowrap; }}
    .passed {{ background: #dcfce7; color: #166534; }}
    .failed {{ background: #fee2e2; color: #991b1b; }}
    .unverified {{ background: #fef3c7; color: #92400e; }}
    .attention {{ background: #fee2e2; color: #991b1b; }}
    a {{ color: #1459b8; font-weight: 650; }}
    li {{ margin: 8px 0; }}
    @media (max-width: 760px) {{ .metrics {{ grid-template-columns: 1fr 1fr; }} }}
  </style>
</head>
<body>
<main>
  <section>
    <div class="eyebrow">Agent DevTools · local run index</div>
    <h1>Recent runs</h1>
    <p class="muted">One place to find task reports and exported diagnostic bundles.</p>
    <div class="metrics">
      {_metric("Reports", len(entries))}
      {_metric("Passed", counts["passed"])}
      {_metric("Failed", counts["failed"] + counts["attention"])}
      {_metric("Unverified", counts["unverified"])}
    </div>
  </section>
  <section>
    <h2>Reports</h2>
    <div class="table-wrap">
      <table>
        <thead><tr><th>When (UTC)</th><th>Type</th><th>Task</th>
          <th>Result</th><th>Actions</th><th>Details</th><th>Open</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </section>
  <section>
    <h2>Diagnostic bundles</h2>
    <ul>{bundle_html}</ul>
  </section>
</main>
</body>
</html>
"""


def _metric(label: str, value: int) -> str:
    return (
        f'<div class="metric"><span>{escape(label)}</span>'
        f"<strong>{value}</strong></div>"
    )


def _entry_row(entry: _RunIndexEntry) -> str:
    status_label = _STATUS_LABELS[entry.status]
    when = entry.timestamp.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"""
      <tr>
        <td>{escape(when)}</td>
        <td>{escape(entry.kind)}</td>
        <td class="task">{escape(entry.task)}</td>
        <td><span class="pill {escape(entry.status)}">{escape(status_label)}</span></td>
        <td>{escape(entry.actions)}</td>
        <td class="detail">{escape(entry.detail)}</td>
        <td><a href="{escape(entry.report_href, quote=True)}">Open report</a></td>
      </tr>
    """


def _write_html(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(html)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


__all__ = ["write_run_index"]
