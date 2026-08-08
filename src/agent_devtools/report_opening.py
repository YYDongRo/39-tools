"""Cross-platform opening of locally generated HTML reports."""

from __future__ import annotations

import platform
import subprocess
import sys
import webbrowser
from pathlib import Path


def open_local_report(report_path: str | Path) -> Path:
    """Open a report with the default browser, with a WSL fallback."""

    absolute_path = Path(report_path).resolve()
    if not absolute_path.is_file():
        raise FileNotFoundError(f"report does not exist: {absolute_path}")

    wsl_error: OSError | None = None
    if _is_wsl():
        try:
            _open_with_explorer(absolute_path)
            return absolute_path
        except OSError as error:
            wsl_error = error

    default_error: Exception | None = None
    try:
        if webbrowser.open(absolute_path.as_uri(), new=2):
            return absolute_path
    except Exception as error:
        default_error = error

    if wsl_error is not None:
        message = (
            "could not open the report in the WSL or Windows browser; "
            f"open it manually: {absolute_path}"
        )
        raise RuntimeError(message) from wsl_error

    message = (
        "could not open the report with the default browser; "
        f"open it manually: {absolute_path}"
    )
    raise RuntimeError(message) from default_error


def _is_wsl() -> bool:
    """Return whether this process is running under WSL."""

    if not sys.platform.startswith("linux"):
        return False
    return "microsoft" in platform.release().casefold()


def _open_with_explorer(report_path: Path) -> None:
    """Launch Windows Explorer after converting a WSL path."""

    try:
        converted = subprocess.run(
            ["wslpath", "-w", str(report_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise OSError("could not convert the WSL report path") from error

    windows_path = converted.stdout.strip()
    if not windows_path:
        raise OSError("wslpath returned an empty report path")

    subprocess.Popen(
        ["explorer.exe", windows_path],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


__all__ = ["open_local_report"]
