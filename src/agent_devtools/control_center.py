"""A small local web page for the current Agent DevTools run."""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import parse_qs, urlsplit

from agent_devtools.config import AgentDevToolsConfig
from agent_devtools.run_index import _discover_entries, write_run_index
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
_RECENT_RUN_LIMIT = 5
_MAX_LAUNCH_BODY_BYTES = 16 * 1024
_MAX_TASK_LENGTH = 2_000
_MAX_LAUNCH_RUNS = 20
_MAX_LAUNCH_STEPS = 100
_INDEX_STATUS_LABELS = {
    "passed": "Passed",
    "failed": "Failed",
    "unverified": "Unverified",
    "attention": "Needs attention",
}


@dataclass(frozen=True)
class _StateLocation:
    root: Path
    state: RunState


@dataclass(frozen=True)
class _SetupCheck:
    name: str
    status: str
    detail: str


def render_control_center(
    root: str | Path,
    *,
    now: datetime | None = None,
    launch_enabled: bool = True,
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
    recent_runs = _render_recent_runs(
        output_root,
        state_root if state_root is not None else output_root,
    )
    index_link = _external_link(index_href, "Open report index ↗", "secondary")
    setup_link = _external_link("setup.html", "Setup & health ↗", "secondary")
    start_link = _external_link(
        "start.html",
        "Start a task ↗" if launch_enabled else "Start page (local only) ↗",
        "primary" if launch_enabled else "secondary",
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
    .section-heading {{ align-items: center; display: flex; flex-wrap: wrap;
      gap: 12px; justify-content: space-between; }}
    .section-heading h2 {{ margin-bottom: 0; }}
    .history {{ display: grid; gap: 10px; }}
    .history-row {{ align-items: center; border: 1px solid #e2e8f0;
      border-radius: 12px; display: grid; gap: 12px;
      grid-template-columns: minmax(0, 1fr) auto auto; padding: 13px 14px; }}
    .history-task {{ font-weight: 750; overflow-wrap: anywhere; }}
    .history-meta, .history-detail {{ color: #64748b; font-size: .82rem;
      line-height: 1.4; margin-top: 4px; }}
    .history-detail {{ color: #53627a; }}
    .history-link {{ color: #1459b8; font-size: .88rem; font-weight: 750;
      white-space: nowrap; }}
    .attention {{ background: #fee2e2; color: #991b1b; }}
    @media (max-width: 650px) {{ dl {{ grid-template-columns: 1fr 1fr; }} }}
    @media (max-width: 650px) {{ .history-row {{ grid-template-columns: 1fr auto; }}
      .history-link {{ grid-column: 1 / -1; }} }}
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
      {start_link}
      {report_link}
      {setup_link}
    </div>
    <div class="notice">{escape(index_note)} Full reports open in a separate
    browser tab; this status page stays available for monitoring.</div>
  </section>
  <section class="panel">
    <div class="section-heading">
      <h2>Recent runs</h2>
      {index_link}
    </div>
    {recent_runs}
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
    config_path: str | Path | None = None,
) -> None:
    """Serve the local control center until interrupted."""

    output_root = _ensure_root(root)
    server = _create_server(
        output_root,
        host=host,
        port=port,
        config_path=config_path,
    )
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
    config_path: str | Path | None = None,
) -> ThreadingHTTPServer:
    launch_enabled = host in {"127.0.0.1", "localhost", "::1"}

    class Handler(_ControlCenterHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(
                *args,
                root=root,
                config_path=config_path,
                launch_enabled=launch_enabled,
                **kwargs,
            )

    server = ThreadingHTTPServer((host, port), Handler)
    # The launcher is deliberately kept on the server instance so the local
    # page can prevent two Browser Use processes from starting at once.
    server._launcher_process = None  # type: ignore[attr-defined]
    server._launcher_lock = Lock()  # type: ignore[attr-defined]
    server._launch_enabled = launch_enabled  # type: ignore[attr-defined]
    return server


class _ControlCenterHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args: Any,
        root: Path,
        config_path: str | Path | None,
        launch_enabled: bool,
        **kwargs: Any,
    ) -> None:
        self._control_root = root
        self._config_path = config_path
        self._launch_enabled = launch_enabled
        super().__init__(*args, directory=str(root), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlsplit(self.path).path
        if path == "/":
            self._send_html(
                render_control_center(
                    self._control_root,
                    launch_enabled=self._launch_enabled,
                )
            )
            return
        if path in {"/start", "/start.html"}:
            self._send_html(
                render_start_page(
                    self._control_root,
                    config_path=self._config_path,
                    enabled=self._launch_enabled,
                )
            )
            return
        if path in {"/setup", "/setup.html"}:
            self._send_html(
                render_setup_page(
                    self._control_root,
                    config_path=self._config_path,
                )
            )
            return
        if path == "/index.html":
            try:
                write_run_index(self._control_root)
            except (OSError, TypeError, ValueError):
                pass
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if urlsplit(self.path).path == "/run":
            self._handle_run()
            return
        self.send_error(404)

    def log_message(self, format: str, *args: Any) -> None:
        return None

    def _handle_run(self) -> None:
        if not self._launch_enabled:
            self._send_html(
                render_start_page(
                    self._control_root,
                    config_path=self._config_path,
                    enabled=False,
                    error="Task launch is disabled unless the server is local-only.",
                ),
                status=403,
            )
            return

        length_header = self.headers.get("Content-Length")
        try:
            content_length = int(length_header or "0")
        except ValueError:
            content_length = _MAX_LAUNCH_BODY_BYTES + 1
        if content_length <= 0 or content_length > _MAX_LAUNCH_BODY_BYTES:
            self._send_html(
                render_start_page(
                    self._control_root,
                    config_path=self._config_path,
                    error="The task form is empty or too large.",
                ),
                status=400,
            )
            return

        try:
            form_data = self.rfile.read(content_length).decode("utf-8")
            values = parse_qs(form_data, keep_blank_values=True)
        except (UnicodeDecodeError, ValueError):
            values = {}
        task = values.get("task", [""])[0].strip()
        runs_text = values.get("runs", ["1"])[0].strip()
        max_steps_text = values.get("max_steps", ["10"])[0].strip()
        headed = values.get("headed", [""])[0] == "on"
        if not task:
            error = "Enter a task before starting the Browser Use agent."
        elif len(task) > _MAX_TASK_LENGTH:
            error = f"Keep the task under {_MAX_TASK_LENGTH} characters."
        elif not runs_text.isdigit() or not 1 <= int(runs_text) <= _MAX_LAUNCH_RUNS:
            error = f"Runs must be a whole number from 1 to {_MAX_LAUNCH_RUNS}."
        elif (
            not max_steps_text.isdigit()
            or not 1 <= int(max_steps_text) <= _MAX_LAUNCH_STEPS
        ):
            error = (
                "Maximum steps must be a whole number from 1 to "
                f"{_MAX_LAUNCH_STEPS}."
            )
        else:
            error = None
        runs = int(runs_text) if runs_text.isdigit() else 1
        max_steps = (
            int(max_steps_text) if max_steps_text.isdigit() else 10
        )

        server = self.server
        launcher_lock = getattr(server, "_launcher_lock", None)
        if error is None and launcher_lock is not None:
            with launcher_lock:
                current = getattr(server, "_launcher_process", None)
                if current is not None and current.poll() is None:
                    error = "A Browser Use task is already running."
                else:
                    location, _ = _discover_state(self._control_root)
                    if (
                        location is not None
                        and location.state.status is RunStateStatus.TRACKING
                    ):
                        error = "An observed task is already tracking."
                    else:
                        error = None
                if error is None:
                    try:
                        command = [
                            sys.executable,
                            "-c",
                            (
                                "from agent_devtools.cli import main; "
                                "raise SystemExit(main())"
                            ),
                            "--task",
                            task,
                            "--runs",
                            str(runs),
                            "--max-steps",
                            str(max_steps),
                        ]
                        if self._config_path is not None:
                            command.extend(
                                ["--config", str(self._config_path)]
                            )
                        if headed:
                            command.append("--headed")
                        process = subprocess.Popen(
                            command,
                            cwd=str(Path.cwd()),
                            stdin=subprocess.DEVNULL,
                            shell=False,
                        )
                    except OSError as launch_error:
                        error = (
                            "Could not start the Browser Use process "
                            f"({type(launch_error).__name__})."
                        )
                    else:
                        setattr(server, "_launcher_process", process)

        if error is not None:
            self._send_html(
                render_start_page(
                    self._control_root,
                    config_path=self._config_path,
                    error=error,
                    task_value=task,
                    runs_value=runs_text,
                    max_steps_value=max_steps_text,
                    headed=headed,
                ),
                status=409 if "already" in error else 400,
            )
            return

        self.send_response(303)
        self.send_header("Location", "/")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_html(self, content: str, *, status: int = 200) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
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


def _external_link(href: str, label: str, style: str) -> str:
    return (
        f'<a class="button {escape(style, quote=True)}" '
        f'href="{escape(href, quote=True)}" target="_blank" '
        f'rel="noopener noreferrer">{escape(label)}</a>'
    )


def _render_recent_runs(root: Path, entries_root: Path) -> str:
    try:
        entries = _discover_entries(entries_root)[:_RECENT_RUN_LIMIT]
    except (OSError, TypeError, ValueError):
        return '<p class="muted">Run history is unavailable.</p>'
    if not entries:
        return '<p class="muted">No completed runs yet.</p>'

    rows: list[str] = []
    for entry in entries:
        report_href = _history_report_href(root, entries_root, entry.report_href)
        if report_href is None:
            continue
        status = entry.status
        status_label = _INDEX_STATUS_LABELS.get(status, "Unverified")
        status_class = escape(status, quote=True)
        when = entry.timestamp.astimezone(UTC).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
        action_label = (
            f"{entry.actions} actions"
            if entry.actions.isdigit()
            else entry.actions
        )
        rows.append(
            """
      <div class="history-row">
        <div>
          <div class="history-task">{task}</div>
          <div class="history-meta">{kind} · {when} · {actions}</div>
          <div class="history-detail">{detail}</div>
        </div>
        <span class="pill {status_class}">{status_label}</span>
        <a class="history-link" href="{href}" target="_blank"
          rel="noopener noreferrer">Open report ↗</a>
      </div>
    """.format(
                task=escape(entry.task),
                kind=escape(entry.kind),
                when=escape(when),
                actions=escape(action_label),
                detail=escape(entry.detail),
                status_class=status_class,
                status_label=escape(status_label),
                href=escape(report_href, quote=True),
            )
        )
    if not rows:
        return '<p class="muted">No completed runs yet.</p>'
    return '<div class="history">' + "".join(rows) + "</div>"


def _history_report_href(
    root: Path,
    state_root: Path,
    report_href: str,
) -> str | None:
    report = Path(report_href)
    if report.is_absolute() or ".." in report.parts:
        return None
    try:
        prefix = state_root.relative_to(root).as_posix()
    except ValueError:
        return None
    return report.as_posix() if prefix == "." else f"{prefix}/{report.as_posix()}"


def render_setup_page(
    root: str | Path,
    *,
    config_path: str | Path | None = None,
) -> str:
    """Render a local, secret-free setup and environment status page."""

    output_root = _ensure_root(root)
    config_file = Path(config_path or "agent_devtools.toml").expanduser()
    config, config_check = _load_setup_config(config_file)
    checks = [config_check, *_setup_checks(config)]
    overall = "attention" if any(
        check.status == "attention" for check in checks
    ) else "ready"
    overall_label = "Needs attention" if overall == "attention" else "Ready"
    rows = "".join(_setup_check_row(check) for check in checks)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent DevTools setup and health</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui,
      -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f3f6fb; color: #172033; }}
    main {{ width: min(820px, calc(100% - 32px)); margin: 48px auto 72px; }}
    .panel {{ background: #fff; border: 1px solid #dce5f0; border-radius: 18px;
      box-shadow: 0 16px 38px rgba(31, 50, 81, .08); padding: 28px;
      margin-bottom: 18px; }}
    .eyebrow {{ color: #42658f; font-size: .75rem; font-weight: 800;
      letter-spacing: .09em; text-transform: uppercase; }}
    h1 {{ margin: 8px 0; font-size: clamp(1.8rem, 4vw, 2.6rem);
      letter-spacing: -.04em; }}
    h2 {{ margin: 0 0 18px; font-size: 1.15rem; }}
    p {{ line-height: 1.55; }}
    .muted {{ color: #64748b; }}
    .topline {{ align-items: center; display: flex; flex-wrap: wrap; gap: 14px;
      margin: 22px 0 12px; }}
    .pill {{ border-radius: 999px; display: inline-block; font-size: .85rem;
      font-weight: 800; padding: 7px 11px; }}
    .ready {{ background: #dcfce7; color: #166534; }}
    .attention {{ background: #fee2e2; color: #991b1b; }}
    .info {{ background: #e0f2fe; color: #075985; }}
    .checks {{ display: grid; gap: 10px; }}
    .check {{ align-items: center; border: 1px solid #e2e8f0; border-radius: 12px;
      display: grid; gap: 14px; grid-template-columns: auto minmax(0, 1fr);
      padding: 13px 14px; }}
    .check-name {{ font-weight: 750; }}
    .check-detail {{ color: #64748b; font-size: .88rem; line-height: 1.4;
      margin-top: 4px; overflow-wrap: anywhere; }}
    .nav {{ display: flex; flex-wrap: wrap; gap: 18px; }}
    .back {{ color: #1459b8; font-weight: 750; text-decoration: none; }}
  </style>
</head>
<body>
<main>
  <section class="panel">
    <div class="eyebrow">Agent DevTools · local setup</div>
    <h1>Setup &amp; health</h1>
    <div class="topline">
      <span class="pill {overall}">{overall_label}</span>
      <span class="muted">Local checks only; no agent run or model call.</span>
    </div>
    <p class="muted">Config source: {_path_label(config_file)} · Trace root:
    {_path_label(output_root)}</p>
  </section>
  <section class="panel">
    <h2>Ready to run</h2>
    <div class="checks">{rows}</div>
  </section>
  <section class="panel">
    <div class="nav">
      <a class="back" href="/">Run status</a>
      <a class="back" href="start.html">Start a task</a>
      <a class="back" href="index.html">Reports</a>
    </div>
    <p class="muted">This page never displays secret values. Provider keys are
    read from environment variables by the agent process, not from this UI.</p>
    <p class="muted">If the provider check says “Not set”, configure
    <code>GEMINI_API_KEY</code>, <code>GOOGLE_API_KEY</code>, or
    <code>OPENAI_API_KEY</code> in the same terminal that starts the dashboard,
    then restart it.</p>
  </section>
</main>
</body>
</html>
"""


def render_start_page(
    root: str | Path,
    *,
    config_path: str | Path | None = None,
    enabled: bool = True,
    error: str | None = None,
    task_value: str = "",
    runs_value: str = "1",
    max_steps_value: str = "10",
    headed: bool = False,
) -> str:
    """Render the local-only Browser Use task launcher."""

    output_root = _ensure_root(root)
    config_file = Path(config_path or "agent_devtools.toml").expanduser()
    error_html = (
        f'<div class="error" role="alert">{escape(error)}</div>'
        if error
        else ""
    )
    if enabled:
        form = f"""
    <form method="post" action="/run">
      <label for="task">Task</label>
      <textarea id="task" name="task" maxlength="2000" required
        placeholder="Example: Open example.com and confirm the page is open.">{escape(task_value)}</textarea>
      <div class="field-grid">
        <div>
          <label for="runs">Runs</label>
          <input id="runs" name="runs" type="number" min="1" max="20"
            value="{escape(runs_value, quote=True)}" required>
          <div class="field-help">1 = one normal run; more runs evaluate stability.</div>
        </div>
        <div>
          <label for="max_steps">Maximum steps</label>
          <input id="max_steps" name="max_steps" type="number" min="1" max="100"
            value="{escape(max_steps_value, quote=True)}" required>
          <div class="field-help">Limit for each Browser Use attempt.</div>
        </div>
      </div>
      <label class="checkbox"><input type="checkbox" name="headed"{' checked' if headed else ''}>
        Show the browser window while it runs</label>
      <button type="submit">Start Browser Use task</button>
    </form>
    """
    else:
        form = """
    <div class="disabled">
      Task launch is disabled because this control center was not bound to a
      loopback address. Restart it with the default local host to enable it.
    </div>
    """
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent DevTools start task</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui,
      -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f3f6fb; color: #172033; }}
    main {{ width: min(760px, calc(100% - 32px)); margin: 48px auto 72px; }}
    .panel {{ background: #fff; border: 1px solid #dce5f0; border-radius: 18px;
      box-shadow: 0 16px 38px rgba(31, 50, 81, .08); padding: 28px;
      margin-bottom: 18px; }}
    .eyebrow {{ color: #42658f; font-size: .75rem; font-weight: 800;
      letter-spacing: .09em; text-transform: uppercase; }}
    h1 {{ margin: 8px 0; font-size: clamp(1.8rem, 4vw, 2.6rem);
      letter-spacing: -.04em; }}
    p {{ line-height: 1.55; }}
    .muted {{ color: #64748b; }}
    label {{ display: block; font-weight: 750; margin: 22px 0 8px; }}
    textarea {{ border: 1px solid #cbd5e1; border-radius: 10px; display: block;
      font: inherit; min-height: 130px; padding: 12px; resize: vertical;
      width: 100%; }}
    textarea:focus {{ border-color: #1459b8; outline: 3px solid #dbeafe; }}
    .field-grid {{ display: grid; gap: 16px; grid-template-columns: 1fr 1fr; }}
    input[type="number"] {{ border: 1px solid #cbd5e1; border-radius: 10px;
      font: inherit; padding: 10px; width: 100%; }}
    input[type="number"]:focus {{ border-color: #1459b8; outline: 3px solid #dbeafe; }}
    .field-help {{ color: #64748b; font-size: .82rem; line-height: 1.4;
      margin-top: 6px; }}
    .checkbox {{ align-items: center; display: flex; font-weight: 500; gap: 9px; }}
    .checkbox input {{ height: 16px; width: 16px; }}
    button {{ background: #1459b8; border: 0; border-radius: 10px; color: #fff;
      cursor: pointer; font: inherit; font-weight: 800; margin-top: 22px;
      padding: 11px 16px; }}
    .notice, .disabled, .error {{ border-radius: 10px; line-height: 1.5;
      margin-top: 18px; padding: 12px 14px; }}
    .notice {{ background: #f8fafc; color: #53627a; }}
    .disabled, .error {{ background: #fee2e2; color: #991b1b; }}
    .nav {{ display: flex; flex-wrap: wrap; gap: 18px; }}
    .back {{ color: #1459b8; font-weight: 750; text-decoration: none; }}
    @media (max-width: 560px) {{ .field-grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<main>
  <section class="panel">
    <div class="eyebrow">Agent DevTools · local control center</div>
    <h1>Start a task</h1>
    <p class="muted">Run the existing Browser Use CLI with the settings below.
    The normal trace and HTML report will appear in the configured trace
    directory.</p>
    {error_html}
    {form}
    <div class="notice">This page accepts a task description and run settings;
    it never executes a command supplied by the form. Provider keys stay in
    environment variables, and the process runs locally with the config from
    <code>{escape(_path_label(config_file))}</code>.</div>
  </section>
  <section class="panel">
    <div class="nav">
      <a class="back" href="/">Run status</a>
      <a class="back" href="setup.html">Setup &amp; health</a>
      <a class="back" href="index.html">Reports</a>
    </div>
    <p class="muted">When the task finishes, use the dashboard's latest report
    link. A task can be started only while this server is bound to localhost.</p>
  </section>
</main>
</body>
</html>
"""


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


def _load_setup_config(
    config_path: Path,
) -> tuple[AgentDevToolsConfig, _SetupCheck]:
    try:
        config = AgentDevToolsConfig.from_file(config_path)
    except FileNotFoundError:
        return (
            AgentDevToolsConfig(),
            _SetupCheck(
                "Configuration",
                "info",
                "No config file; using built-in defaults",
            ),
        )
    except (OSError, TypeError, ValueError) as error:
        return (
            AgentDevToolsConfig(),
            _SetupCheck(
                "Configuration",
                "attention",
                f"Could not load config ({type(error).__name__})",
            ),
        )
    return (
        config,
        _SetupCheck("Configuration", "ready", "Config file loaded"),
    )


def _setup_checks(config: AgentDevToolsConfig) -> tuple[_SetupCheck, ...]:
    checks: list[_SetupCheck] = []
    if config.enabled:
        checks.append(
            _SetupCheck("Recording", "ready", "Action recording is enabled")
        )
    else:
        checks.append(
            _SetupCheck(
                "Recording",
                "attention",
                "Recording is disabled; no trace or report will be created",
            )
        )

    checks.append(_provider_key_check())
    checks.append(_browser_check(config))
    checks.append(_trace_directory_check(config.trace_directory))
    checks.append(
        _SetupCheck(
            "Screenshots",
            "ready" if config.screenshots else "info",
            (
                "Before/after screenshots are enabled"
                if config.screenshots
                else "Disabled; actions and state are still recorded"
            ),
        )
    )
    checks.append(
        _SetupCheck(
            "Redaction",
            "ready" if config.redact_sensitive_data else "attention",
            (
                "Sensitive metadata redaction is enabled"
                if config.redact_sensitive_data
                else "Disabled; review traces before sharing"
            ),
        )
    )
    return tuple(checks)


def _provider_key_check() -> _SetupCheck:
    provider = os.getenv("AGENT_DEVTOOLS_LLM_PROVIDER", "auto").strip().lower()
    if provider not in {"auto", "gemini", "openai"}:
        return _SetupCheck(
            "Provider key",
            "attention",
            "Unknown provider selection",
        )
    gemini = bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
    openai = bool(os.getenv("OPENAI_API_KEY"))
    if provider == "gemini" and gemini:
        return _SetupCheck("Provider key", "ready", "Gemini key is available")
    if provider == "openai" and openai:
        return _SetupCheck("Provider key", "ready", "OpenAI key is available")
    if provider == "auto" and gemini and openai:
        return _SetupCheck(
            "Provider key",
            "attention",
            "Multiple provider keys; choose Gemini or OpenAI explicitly",
        )
    if provider == "auto" and (gemini or openai):
        return _SetupCheck(
            "Provider key",
            "ready",
            "A provider key is available",
        )
    return _SetupCheck(
        "Provider key",
        "info",
        "Not set; required when the Browser Use CLI creates the agent",
    )


def _browser_check(config: AgentDevToolsConfig) -> _SetupCheck:
    path = config.browser_executable_path
    if path is None:
        return _SetupCheck(
            "Browser",
            "ready",
            "Using Browser Use's managed browser",
        )
    if path.is_file():
        return _SetupCheck(
            "Browser",
            "ready",
            "Configured browser executable found",
        )
    return _SetupCheck(
        "Browser",
        "attention",
        "Configured browser executable not found",
    )


def _trace_directory_check(configured: Path) -> _SetupCheck:
    path = configured.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if path.exists() and not path.is_dir():
        return _SetupCheck(
            "Trace directory",
            "attention",
            "Configured path is not a directory",
        )
    if not path.exists():
        return _SetupCheck(
            "Trace directory",
            "info",
            "Directory will be created on first run",
        )
    if os.access(path, os.W_OK):
        return _SetupCheck(
            "Trace directory",
            "ready",
            "Trace directory is writable",
        )
    return _SetupCheck(
        "Trace directory",
        "attention",
        "Trace directory is not writable",
    )


def _setup_check_row(check: _SetupCheck) -> str:
    return (
        f'<div class="check"><span class="pill {escape(check.status)}">'
        f'{escape(check.status.title())}</span><div><div class="check-name">'
        f'{escape(check.name)}</div><div class="check-detail">'
        f'{escape(check.detail)}</div></div></div>'
    )


def _path_label(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(Path.cwd().resolve())
    except (OSError, ValueError):
        return path.name or path.as_posix()
    return relative.as_posix() or "."


__all__ = [
    "render_control_center",
    "render_setup_page",
    "render_start_page",
    "serve_control_center",
]
