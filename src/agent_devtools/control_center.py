"""A small local web page for the current Agent DevTools run."""

from __future__ import annotations

import webbrowser
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from agent_devtools.run_index import write_run_index
from agent_devtools.run_state import RunState, RunStateStatus, read_run_state


_STATUS_LABELS = {
    RunStateStatus.NOT_CONFIGURED: "Not configured",
    RunStateStatus.READY: "Ready",
    RunStateStatus.TRACKING: "Tracking",
    RunStateStatus.PASSED: "Passed",
    RunStateStatus.FAILED: "Failed",
    RunStateStatus.UNVERIFIED: "Unverified",
    RunStateStatus.ERRORED: "Errored",
}
_STALE_RUN_AFTER = timedelta(minutes=2)


@dataclass(frozen=True)
class _StateLocation:
    root: Path
    state: RunState


def render_control_center(
    root: str | Path,
    *,
    now: datetime | None = None,
) -> str:
    """Render the current local run state as a dependency-free HTML page."""

    output_root = _ensure_root(root)
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    location, state_error = _discover_state(output_root)
    state = location.state if location is not None else None
    state_root = location.root if location is not None else None
    report_href = _report_href(output_root, state_root, state)
    try:
        _write_report_indexes(output_root, state_root)
        index_error = None
    except (OSError, TypeError, ValueError) as error:
        index_error = f"Could not update report index ({type(error).__name__})"

    if state is None:
        status_value = RunStateStatus.NOT_CONFIGURED
        status_label = "Waiting for a run"
        task = "Start an observed agent run to see its live status here."
        action_count = "—"
        last_action_type = "—"
        updated_at = "—"
        details = state_error or "No run-state.json has been created yet."
        trace_source = "—"
        is_stale = False
        refresh = ""
    else:
        status_value = state.status
        status_label = _STATUS_LABELS[state.status]
        task = state.task or "Task not provided"
        action_count = str(state.action_count)
        last_action_type = state.last_action_type or "—"
        updated_at = _format_timestamp(state.updated_at)
        details = _state_details(state)
        trace_source = _relative_source(output_root, state_root)
        is_stale = _is_stale(state, current_time)
        if is_stale:
            status_label = "Tracking · possibly interrupted"
            details = (
                f"No update for {_format_age(current_time - state.updated_at)}; "
                "the process may have stopped"
            )
        refresh = '<meta http-equiv="refresh" content="2">' if (
            state.status is RunStateStatus.TRACKING
        ) else ""

    index_note = index_error or "Reports are listed in the local index."
    index_href = _index_href(output_root, state_root)
    report_link = (
        f'<a class="button primary" href="{escape(report_href, quote=True)}" '
        'target="_blank" rel="noopener noreferrer">'
        "Open full report ↗</a>"
        if report_href is not None
        else '<span class="muted">No completed report yet</span>'
    )
    index_link = (
        f'<a class="button secondary" href="{escape(index_href, quote=True)}" '
        'target="_blank" rel="noopener noreferrer">'
        "Open report index ↗</a>"
    )
    status_class = escape(
        f"{status_value.value}{' stale' if is_stale else ''}",
        quote=True,
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {refresh}
  <title>Agent DevTools control center</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui,
      -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f3f6fb; color: #172033; }}
    main {{ width: min(900px, calc(100% - 32px)); margin: 48px auto 72px; }}
    .panel {{ background: #fff; border: 1px solid #dce5f0; border-radius: 18px;
      box-shadow: 0 16px 38px rgba(31, 50, 81, .08); padding: 28px;
      margin-bottom: 18px; }}
    .eyebrow {{ color: #42658f; font-size: .75rem; font-weight: 800;
      letter-spacing: .09em; text-transform: uppercase; }}
    h1 {{ margin: 8px 0 8px; font-size: clamp(1.8rem, 4vw, 2.6rem);
      letter-spacing: -.04em; }}
    h2 {{ margin: 0 0 18px; font-size: 1.15rem; }}
    p {{ line-height: 1.55; }}
    .muted {{ color: #64748b; }}
    .status-row {{ align-items: center; display: flex; flex-wrap: wrap; gap: 14px;
      margin: 22px 0 18px; }}
    .pill {{ border-radius: 999px; display: inline-block; font-size: .85rem;
      font-weight: 800; padding: 7px 11px; }}
    .tracking {{ background: #dbeafe; color: #1d4ed8; }}
    .stale {{ background: #fef3c7; color: #92400e; }}
    .passed {{ background: #dcfce7; color: #166534; }}
    .failed, .errored {{ background: #fee2e2; color: #991b1b; }}
    .unverified, .not_configured, .ready {{ background: #fef3c7; color: #92400e; }}
    .task {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px;
      padding: 14px; }}
    .task-label, dt {{ color: #64748b; font-size: .75rem; font-weight: 800;
      letter-spacing: .05em; text-transform: uppercase; }}
    .task-text {{ margin: 7px 0 0; white-space: pre-wrap; word-break: break-word; }}
    dl {{ display: grid; gap: 14px 28px; grid-template-columns: repeat(4, 1fr);
      margin: 22px 0 0; }}
    dt {{ margin-bottom: 5px; }} dd {{ margin: 0; word-break: break-word; }}
    .actions {{ align-items: center; display: flex; flex-wrap: wrap; gap: 12px;
      margin-top: 24px; }}
    .button {{ border-radius: 10px; display: inline-block; font-weight: 750;
      padding: 10px 14px; text-decoration: none; }}
    .primary {{ background: #1459b8; color: #fff; }}
    .secondary {{ border: 1px solid #cbd5e1; color: #1459b8; }}
    .notice {{ background: #f8fafc; border-radius: 10px; color: #53627a;
      font-size: .9rem; margin-top: 18px; padding: 11px 13px; }}
    @media (max-width: 650px) {{ dl {{ grid-template-columns: 1fr 1fr; }} }}
    @media (max-width: 430px) {{ dl {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<main>
  <section class="panel">
    <div class="eyebrow">Agent DevTools · local control center</div>
    <h1>Run status</h1>
    <div class="status-row">
      <span class="pill {status_class}">{escape(status_label)}</span>
      <span class="muted">This page reads local trace files only.</span>
    </div>
    <div class="task">
      <div class="task-label">Current task</div>
      <div class="task-text">{escape(task)}</div>
    </div>
    <dl>
      <div><dt>Actions</dt><dd>{escape(action_count)}</dd></div>
      <div><dt>Last action</dt><dd>{escape(last_action_type)}</dd></div>
      <div><dt>Last update (UTC)</dt><dd>{escape(updated_at)}</dd></div>
      <div><dt>Details</dt><dd>{escape(details)}</dd></div>
      <div><dt>Trace source</dt><dd>{escape(trace_source)}</dd></div>
    </dl>
    <div class="actions">
      {report_link}
      {index_link}
    </div>
    <div class="notice">{escape(index_note)} Full reports open in a separate
    browser tab; this status page stays available for monitoring.</div>
  </section>
  <section class="panel">
    <h2>What this means</h2>
    <p class="muted">Tracking means the observer is active. Passed or failed is
    the final task result, not merely whether an individual action ran.</p>
    <p class="muted">The page refreshes every two seconds while a run is
    tracking. If no update arrives for two minutes, it shows a warning instead
    of guessing that the task failed. Stop the server with Ctrl+C.</p>
  </section>
</main>
</body>
</html>
"""


def serve_control_center(
    root: str | Path = Path("trace"),
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = False,
) -> None:
    """Serve the local control center until interrupted."""

    output_root = _ensure_root(root)
    server = _create_server(output_root, host=host, port=port)
    url = f"http://{host}:{server.server_port}/"
    print(f"Agent DevTools control center: {url}")
    print(f"Trace root: {output_root.resolve()}")
    if open_browser:
        try:
            webbrowser.open(url, new=2)
        except Exception as error:
            print(f"Control center could not be opened: {type(error).__name__}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Control center stopped.")
    finally:
        server.server_close()


def _create_server(
    root: Path,
    *,
    host: str,
    port: int,
) -> ThreadingHTTPServer:
    class Handler(_ControlCenterHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, root=root, **kwargs)

    return ThreadingHTTPServer((host, port), Handler)


class _ControlCenterHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args: Any,
        root: Path,
        **kwargs: Any,
    ) -> None:
        self._control_root = root
        super().__init__(*args, directory=str(root), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlsplit(self.path).path
        if path == "/":
            self._send_html(render_control_center(self._control_root))
            return
        if path == "/index.html":
            try:
                write_run_index(self._control_root)
            except (OSError, TypeError, ValueError):
                pass
        super().do_GET()

    def log_message(self, format: str, *args: Any) -> None:
        return None

    def _send_html(self, content: str) -> None:
        body = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _ensure_root(root: str | Path) -> Path:
    output_root = Path(root).expanduser()
    if output_root.exists() and not output_root.is_dir():
        raise ValueError(f"control center root is not a directory: {output_root}")
    resolved = output_root.resolve()
    home = Path.home().resolve()
    if resolved == Path(resolved.anchor) or resolved == home:
        raise ValueError("control center root must be a project subdirectory")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _discover_state(root: Path) -> tuple[_StateLocation | None, str | None]:
    """Find the newest valid state directly below ``root`` or one level down."""

    candidates = [root / "run-state.json"]
    candidates.extend(sorted(root.glob("*/run-state.json")))
    locations: list[_StateLocation] = []
    errors: list[str] = []
    for path in candidates:
        if not path.is_file():
            continue
        try:
            locations.append(_StateLocation(path.parent, read_run_state(path)))
        except (OSError, TypeError, ValueError) as error:
            errors.append(type(error).__name__)

    if locations:
        locations.sort(
            key=lambda location: (
                location.state.updated_at,
                location.root.as_posix(),
            ),
            reverse=True,
        )
        return locations[0], None
    if errors:
        return None, f"Run state is unavailable ({errors[0]})."
    return None, None


def _write_report_indexes(root: Path, state_root: Path | None) -> None:
    roots = {root}
    if state_root is not None:
        roots.add(state_root)
    for index_root in sorted(roots, key=lambda path: path.as_posix()):
        write_run_index(index_root)


def _report_href(
    root: Path,
    state_root: Path | None,
    state: RunState | None,
) -> str | None:
    if state is None or state_root is None or state.report_path is None:
        return None
    report = state_root / state.report_path
    try:
        report.resolve().relative_to(state_root.resolve())
        relative = report.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    if not report.is_file():
        return None
    return relative.as_posix()


def _relative_source(root: Path, state_root: Path | None) -> str:
    if state_root is None:
        return "—"
    try:
        relative = state_root.relative_to(root)
    except ValueError:
        return "—"
    return relative.as_posix() or "."


def _index_href(root: Path, state_root: Path | None) -> str:
    if state_root is None:
        return "index.html"
    try:
        return (state_root.relative_to(root) / "index.html").as_posix()
    except ValueError:
        return "index.html"


def _state_details(state: RunState) -> str:
    if state.status is RunStateStatus.ERRORED:
        return state.error_type or state.issue_code or "Agent error"
    if state.issue_code:
        return state.issue_code
    if state.status is RunStateStatus.TRACKING:
        return "Observer is active"
    return "Final task result recorded"


def _format_timestamp(value: object) -> str:
    if not isinstance(value, datetime):
        return "—"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _is_stale(state: RunState, now: datetime) -> bool:
    return (
        state.status is RunStateStatus.TRACKING
        and now.astimezone(UTC) - state.updated_at.astimezone(UTC)
        >= _STALE_RUN_AFTER
    )


def _format_age(age: timedelta) -> str:
    seconds = max(0, int(age.total_seconds()))
    minutes, remaining_seconds = divmod(seconds, 60)
    if minutes:
        return f"{minutes}m {remaining_seconds}s"
    return f"{remaining_seconds}s"


__all__ = ["render_control_center", "serve_control_center"]
