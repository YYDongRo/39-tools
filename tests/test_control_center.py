from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent_devtools.control_center import render_control_center
from agent_devtools.run_state import (
    RunState,
    RunStateStatus,
    write_run_state,
)


def _write_state(
    root: Path,
    status: RunStateStatus,
    *,
    action_count: int = 2,
    report_path: Path | None = None,
) -> None:
    started_at = datetime(2026, 8, 9, 12, tzinfo=UTC)
    write_run_state(
        RunState(
            status=status,
            updated_at=datetime(2026, 8, 9, 12, 0, 2, tzinfo=UTC),
            run_id="20260809T120000Z-demo",
            task="Open the requested page",
            started_at=started_at,
            action_count=action_count,
            report_path=report_path,
            issue_code="target_not_found" if status is RunStateStatus.FAILED else None,
            error_type="RuntimeError" if status is RunStateStatus.ERRORED else None,
        ),
        root / "run-state.json",
    )


def test_control_center_shows_tracking_state_and_auto_refresh(tmp_path: Path) -> None:
    _write_state(tmp_path, RunStateStatus.TRACKING, action_count=3)

    html = render_control_center(tmp_path)

    assert "Tracking" in html
    assert "Open the requested page" in html
    assert "3" in html
    assert 'http-equiv="refresh" content="2"' in html
    assert "No completed report yet" in html
    assert str(tmp_path.resolve()) not in html


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
    assert "target_not_found" in html
    assert 'href="20260809T120000Z-demo/report.html"' in html
    assert "http-equiv=\"refresh\"" not in html
    assert str(tmp_path.resolve()) not in html


def test_control_center_handles_first_run_without_state(tmp_path: Path) -> None:
    html = render_control_center(tmp_path)

    assert "Waiting for a run" in html
    assert "No run-state.json has been created yet." in html
    assert 'href="index.html"' in html


def test_control_center_handles_invalid_state_without_exposing_details(
    tmp_path: Path,
) -> None:
    (tmp_path / "run-state.json").write_text(
        '{"status": "broken", "private": "do-not-show"}',
        encoding="utf-8",
    )

    html = render_control_center(tmp_path)

    assert "Run state is unavailable (ValueError)." in html
    assert "do-not-show" not in html


def test_control_center_rejects_broad_roots() -> None:
    with pytest.raises(ValueError, match="project subdirectory"):
        render_control_center(Path.home())
