from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from threading import Thread
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.control_center import (
    _create_server,
    render_control_center,
    render_setup_page,
    render_start_page,
)
from agent_devtools.run_state import (
    RunState,
    RunStateStatus,
    write_run_state,
)
from agent_devtools.serialization import write_session_json
from agent_devtools.session import ActionSession
from agent_devtools.verification import VerificationResult


def _write_state(
    root: Path,
    status: RunStateStatus,
    *,
    action_count: int = 2,
    last_action_type: str | None = None,
    report_path: Path | None = None,
    task: str = "Open the requested page",
) -> None:
    started_at = datetime(2026, 8, 9, 12, tzinfo=UTC)
    write_run_state(
        RunState(
            status=status,
            updated_at=datetime(2026, 8, 9, 12, 0, 2, tzinfo=UTC),
            run_id="20260809T120000Z-demo",
            task=task,
            started_at=started_at,
            action_count=action_count,
            last_action_type=last_action_type,
            report_path=report_path,
            issue_code="target_not_found" if status is RunStateStatus.FAILED else None,
            error_type="RuntimeError" if status is RunStateStatus.ERRORED else None,
        ),
        root / "run-state.json",
    )


def test_control_center_shows_tracking_state_and_auto_refresh(tmp_path: Path) -> None:
    _write_state(
        tmp_path,
        RunStateStatus.TRACKING,
        action_count=3,
        last_action_type="click",
    )

    html = render_control_center(
        tmp_path,
        now=datetime(2026, 8, 9, 12, 0, 10, tzinfo=UTC),
    )

    assert "Tracking" in html
    assert "Latest run" in html
    assert "Open the requested page" in html
    assert "Report pending" in html
    assert 'http-equiv="refresh" content="2"' in html
    assert "What this means" not in html
    assert "Last action" not in html
    assert "Actions" not in html
    assert "possibly interrupted" not in html
    assert str(tmp_path.resolve()) not in html


def test_control_center_warns_when_tracking_state_is_stale(tmp_path: Path) -> None:
    _write_state(
        tmp_path,
        RunStateStatus.TRACKING,
        action_count=3,
        last_action_type="fill",
    )

    html = render_control_center(
        tmp_path,
        now=datetime(2026, 8, 9, 12, 2, 5, tzinfo=UTC),
    )

    assert "Tracking · possibly interrupted" in html
    assert "No update for" not in html
    assert "the process may have stopped" not in html


def test_control_center_links_latest_report_with_relative_path(
    tmp_path: Path,
) -> None:
    report_path = Path("20260809T120000Z-demo") / "report.html"
    report = tmp_path / report_path
    report.parent.mkdir(parents=True)
    report.write_text("<html>report</html>", encoding="utf-8")
    _write_state(tmp_path, RunStateStatus.FAILED, report_path=report_path)

    html = render_control_center(tmp_path)

    assert "Failed" in html
    assert 'href="20260809T120000Z-demo/report.html"' in html
    assert 'target="_blank" rel="noopener noreferrer"' in html
    assert "Open report ↗" in html
    assert "Open full report" not in html
    assert "target_not_found" not in html
    assert "Details" not in html
    assert "What this means" not in html
    assert "http-equiv=\"refresh\"" not in html
    assert str(tmp_path.resolve()) not in html


def test_control_center_serves_report_from_same_local_app(tmp_path: Path) -> None:
    report_path = Path("demo") / "report.html"
    report = tmp_path / report_path
    report.parent.mkdir(parents=True)
    report.write_text("<html>local report</html>", encoding="utf-8")
    _write_state(tmp_path, RunStateStatus.PASSED, report_path=report_path)

    server = _create_server(tmp_path, host="127.0.0.1", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with urlopen(f"{base_url}/") as response:
            control_center = response.read().decode("utf-8")
        with urlopen(f"{base_url}/demo/report.html") as response:
            report_html = response.read().decode("utf-8")
        with urlopen(f"{base_url}/setup.html") as response:
            setup_html = response.read().decode("utf-8")
        with urlopen(f"{base_url}/start.html") as response:
            start_html = response.read().decode("utf-8")
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    assert 'href="demo/report.html"' in control_center
    assert 'target="_blank" rel="noopener noreferrer"' in control_center
    assert report_html == "<html>local report</html>"
    assert "Setup &amp; health" in setup_html
    assert "Local checks only" in setup_html
    assert "← Back to home" in setup_html
    assert 'href="/"' in setup_html
    assert 'href="start.html"' not in setup_html
    assert 'href="index.html"' not in setup_html
    assert "GEMINI_API_KEY" in setup_html
    assert "Start a task" in start_html
    assert "Start Browser Use task" in start_html
    assert 'name="runs"' in start_html
    assert 'name="max_steps"' in start_html
    assert '<details class="advanced">' in start_html
    assert "Open a visible browser window" in start_html
    assert start_html.count('href="/"') == 1
    assert 'href="setup.html"' not in start_html
    assert 'href="index.html"' not in start_html


def test_start_page_is_local_only_and_does_not_show_secrets(
    tmp_path: Path,
) -> None:
    html = render_start_page(
        tmp_path,
        config_path=tmp_path / "private-config.toml",
        enabled=False,
    )

    assert "Task launch is disabled" in html
    assert str(tmp_path.resolve()) not in html
    assert "GOOGLE_API_KEY" not in html
    assert "← Back to home" in html


def test_start_route_launches_only_the_fixed_browser_use_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launched: dict[str, object] = {}

    class FakeProcess:
        def poll(self) -> None:
            return None

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        launched["command"] = command
        launched.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(
        "agent_devtools.control_center.subprocess.Popen",
        fake_popen,
    )
    server = _create_server(tmp_path, host="127.0.0.1", port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        request = Request(
            f"{base_url}/run",
            data=urlencode(
                {
                    "task": "Open example.test",
                    "runs": "3",
                    "max_steps": "7",
                    "headed": "on",
                }
            ).encode("utf-8"),
            method="POST",
        )
        with urlopen(request) as response:
            dashboard = response.read().decode("utf-8")
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()

    command = launched["command"]
    assert isinstance(command, list)
    assert command[0] == sys.executable
    assert command[1:4] == [
        "-c",
        "from agent_devtools.cli import main; raise SystemExit(main())",
        "--task",
    ]
    assert "Open example.test" in command
    assert "--runs" in command
    assert command[command.index("--runs") + 1] == "3"
    assert "--max-steps" in command
    assert command[command.index("--max-steps") + 1] == "7"
    assert "--headed" in command
    assert launched["stdin"] is subprocess.DEVNULL
    assert launched["shell"] is False
    assert launched["cwd"] == str(Path.cwd())
    assert "Start a task" in dashboard
    assert "Open example.test" not in dashboard


def test_setup_page_reports_safe_configuration_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "agent_devtools.toml"
    config_path.write_text(
        """[agent_devtools]
screenshots = false
redact_sensitive_data = true
trace_directory = "trace-output"
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("AGENT_DEVTOOLS_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "secret-key-value")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    html = render_setup_page(tmp_path, config_path=config_path)

    assert "Setup &amp; health" in html
    assert "Config file loaded" in html
    assert "A provider key is available" in html
    assert "Disabled; actions and state are still recorded" in html
    assert "secret-key-value" not in html
    assert str(tmp_path.resolve()) not in html

    monkeypatch.setenv("OPENAI_API_KEY", "another-secret")
    conflict_html = render_setup_page(tmp_path, config_path=config_path)
    assert "Needs attention" in conflict_html
    assert "Multiple provider keys" in conflict_html


def test_control_center_lists_recent_runs(tmp_path: Path) -> None:
    run_dir = tmp_path / "20260809T120000Z-history"
    run_dir.mkdir()
    session = ActionSession(
        goal="Find the requested item",
        actions=[
            ActionRecord(
                action_type="click",
                arguments={"selector": "#item"},
                start_time=datetime(2026, 8, 9, 12, tzinfo=UTC),
                duration_ms=42,
                status=ActionStatus.SUCCESS,
            )
        ],
        verification=VerificationResult(
            expected_state="the requested item is open",
            observed_state="the requested item is open",
            passed=True,
        ),
    )
    write_session_json(session, run_dir / "session.json")
    (run_dir / "report.html").write_text(
        "<html>history report</html>",
        encoding="utf-8",
    )
    _write_state(
        tmp_path,
        RunStateStatus.PASSED,
        action_count=1,
        last_action_type="click",
        report_path=Path("20260809T120000Z-history") / "report.html",
    )

    html = render_control_center(tmp_path)

    assert "Recent runs" in html
    assert "Find the requested item" in html
    assert "Passed" in html
    assert 'href="20260809T120000Z-history/report.html"' in html
    assert "Open report ↗" in html
    assert "Task run" not in html
    assert "2026-08-09" not in html
    assert "1 actions" not in html
    assert "Final task check passed" not in html


def test_control_center_discovers_newest_nested_trace_root(tmp_path: Path) -> None:
    older_root = tmp_path / "playwright"
    newer_root = tmp_path / "browser-use"
    older_root.mkdir()
    newer_root.mkdir()
    _write_state(
        older_root,
        RunStateStatus.PASSED,
        action_count=1,
        task="Older task",
    )
    _write_state(
        newer_root,
        RunStateStatus.TRACKING,
        action_count=4,
        task="Newer task",
    )
    # Make the selection deterministic without relying on filesystem mtime.
    state_path = newer_root / "run-state.json"
    state_path.write_text(
        state_path.read_text(encoding="utf-8").replace(
            "2026-08-09T12:00:02+00:00",
            "2026-08-09T12:00:03+00:00",
        ),
        encoding="utf-8",
    )

    html = render_control_center(tmp_path)

    assert "Tracking" in html
    assert "Newer task" in html
    assert "Older task" not in html


def test_control_center_handles_first_run_without_state(tmp_path: Path) -> None:
    html = render_control_center(tmp_path)

    assert "<title>39 tools</title>" in html
    assert "<h1>39 tools</h1>" in html
    assert "class=\"button primary\"" in html
    assert html.count('class="button secondary"') >= 2
    assert "Latest run" not in html
    assert 'href="index.html"' in html


def test_control_center_handles_invalid_state_without_exposing_details(
    tmp_path: Path,
) -> None:
    (tmp_path / "run-state.json").write_text(
        '{"status": "broken", "private": "do-not-show"}',
        encoding="utf-8",
    )

    html = render_control_center(tmp_path)

    assert "Unavailable" in html
    assert "Could not read the latest run." in html
    assert "do-not-show" not in html


def test_control_center_rejects_broad_roots() -> None:
    with pytest.raises(ValueError, match="project subdirectory"):
        render_control_center(Path.home())
