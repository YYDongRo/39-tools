from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import agent_devtools.report_opening as report_opening


def _report(tmp_path: Path) -> Path:
    report_path = tmp_path / "report.html"
    report_path.write_text("<html></html>", encoding="utf-8")
    return report_path


def test_detects_wsl_from_linux_kernel_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(report_opening.sys, "platform", "linux")
    monkeypatch.setattr(
        report_opening.platform,
        "release",
        lambda: "5.15.153.1-microsoft-standard-WSL2",
    )

    assert report_opening._is_wsl() is True


def test_open_local_report_uses_default_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = _report(tmp_path)
    opened: list[tuple[str, int]] = []

    monkeypatch.setattr(
        report_opening.webbrowser,
        "open",
        lambda url, *, new: opened.append((url, new)) or True,
    )
    monkeypatch.setattr(report_opening, "_is_wsl", lambda: False)

    assert (
        report_opening.open_local_report(report_path) == report_path.resolve()
    )
    assert opened == [(report_path.resolve().as_uri(), 2)]


def test_open_local_report_prefers_explorer_in_wsl(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = _report(tmp_path)
    launched: list[tuple[list[str], dict[str, object]]] = []
    default_opened: list[bool] = []
    converted_path = r"C:\tmp\report.html"

    def unexpected_default_open(*args: object, **kwargs: object) -> bool:
        default_opened.append(True)
        return True

    monkeypatch.setattr(
        report_opening.webbrowser,
        "open",
        unexpected_default_open,
    )
    monkeypatch.setattr(report_opening, "_is_wsl", lambda: True)
    monkeypatch.setattr(
        report_opening.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout=converted_path + "\n", stderr=""
        ),
    )
    monkeypatch.setattr(
        report_opening.subprocess,
        "Popen",
        lambda command, **kwargs: launched.append((command, kwargs)),
    )

    assert report_opening.open_local_report(report_path) == report_path.resolve()
    assert launched == [
        (
            ["explorer.exe", converted_path],
            {
                "stdin": report_opening.subprocess.DEVNULL,
                "stdout": report_opening.subprocess.DEVNULL,
                "stderr": report_opening.subprocess.DEVNULL,
                "start_new_session": True,
            },
        )
    ]
    assert default_opened == []


def test_open_local_report_uses_default_browser_if_wsl_fallback_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = _report(tmp_path)
    opened: list[tuple[str, int]] = []

    monkeypatch.setattr(report_opening, "_is_wsl", lambda: True)

    def missing_wslpath(*args: object, **kwargs: object) -> object:
        raise FileNotFoundError("wslpath")

    monkeypatch.setattr(report_opening.subprocess, "run", missing_wslpath)
    monkeypatch.setattr(
        report_opening.webbrowser,
        "open",
        lambda url, *, new: opened.append((url, new)) or True,
    )

    assert (
        report_opening.open_local_report(report_path) == report_path.resolve()
    )
    assert opened == [(report_path.resolve().as_uri(), 2)]


def test_open_local_report_keeps_manual_path_when_no_fallback_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = _report(tmp_path)
    monkeypatch.setattr(
        report_opening.webbrowser,
        "open",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(report_opening, "_is_wsl", lambda: False)

    with pytest.raises(RuntimeError, match="open it manually"):
        report_opening.open_local_report(report_path)


def test_open_local_report_requires_an_existing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="report does not exist"):
        report_opening.open_local_report(tmp_path / "missing.html")
