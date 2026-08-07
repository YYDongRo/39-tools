"""Run a deterministic desktop-style agent through the generic observer.

The demo uses an in-memory desktop surface, so it needs no browser, API key,
or platform-specific automation package. By default the agent clicks the
wrong setting to demonstrate that successful actions do not guarantee a
successful task. Pass ``--correct`` to see the passing version.
"""

from __future__ import annotations

import argparse
import struct
import webbrowser
import zlib
from pathlib import Path

from agent_devtools import (
    FinalStateObservation,
    VerificationResult,
    observe_agent,
)
from agent_devtools.serialization import read_session_json


TASK = "Open Settings and enable dark mode."
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class DesktopSurface:
    """Small in-memory surface that behaves like a desktop application."""

    def __init__(self) -> None:
        self.screen = "home"
        self.dark_mode_enabled = False
        self.notifications_enabled = False
        self.last_clicked: str | None = None

    def open_app(self, app_name: str) -> None:
        if app_name != "Settings":
            raise ValueError(f"unknown app: {app_name}")
        self.screen = "settings"

    def click(self, target: str) -> None:
        if self.screen != "settings":
            raise RuntimeError("Settings is not open")
        if target == "dark-mode-toggle":
            self.dark_mode_enabled = True
        elif target == "notifications-toggle":
            self.notifications_enabled = True
        else:
            raise ValueError(f"unknown settings target: {target}")
        self.last_clicked = target

    def state(self) -> dict[str, object]:
        return {
            "screen": self.screen,
            "dark_mode_enabled": self.dark_mode_enabled,
            "notifications_enabled": self.notifications_enabled,
            "last_clicked": self.last_clicked,
        }


class DesktopTools:
    """The tool dispatcher that the agent keeps and calls during a run."""

    def __init__(self, surface: DesktopSurface) -> None:
        self._surface = surface

    def open_app(self, app_name: str) -> None:
        self._surface.open_app(app_name)

    def click(self, target: str) -> None:
        self._surface.click(target)


class DemoAgent:
    def __init__(
        self,
        tools: DesktopTools,
        task: str = TASK,
        *,
        click_target: str,
    ) -> None:
        self.task = task
        self.tools = tools
        self.click_target = click_target

    def run(self, task: str) -> str:
        if task != self.task:
            raise ValueError("the observer passed a different task")
        self.tools.open_app("Settings")
        self.tools.click(self.click_target)
        return "done"


def _verify(observation: FinalStateObservation) -> VerificationResult:
    state = observation.state
    passed = (
        state["screen"] == "settings"
        and state["dark_mode_enabled"] is True
    )
    observed = (
        f"screen={state['screen']}, "
        f"dark_mode_enabled={state['dark_mode_enabled']}"
    )
    return VerificationResult(
        expected_state="Settings is open with dark mode enabled",
        observed_state=observed,
        passed=passed,
        evidence={"state": state},
        failure_reason=(
            None
            if passed
            else "the agent clicked a setting, but dark mode is still disabled"
        ),
    )


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _draw_rectangle(
    rows: list[bytearray],
    left: int,
    top: int,
    right: int,
    bottom: int,
    color: tuple[int, int, int],
) -> None:
    pixel = bytes(color)
    height = len(rows)
    width = len(rows[0]) // 3
    for y in range(max(0, top), min(height, bottom)):
        row = rows[y]
        for x in range(max(0, left), min(width, right)):
            offset = x * 3
            row[offset : offset + 3] = pixel


def _render_surface(surface: DesktopSurface) -> bytes:
    """Render a small valid PNG without adding an image dependency."""

    width, height = 640, 360
    rows = [bytearray(bytes((238, 242, 247)) * width) for _ in range(height)]
    _draw_rectangle(rows, 0, 0, width, 54, (30, 41, 59))
    _draw_rectangle(rows, 48, 84, 592, 320, (255, 255, 255))
    _draw_rectangle(rows, 80, 112, 300, 128, (148, 163, 184))
    _draw_rectangle(rows, 80, 146, 250, 164, (203, 213, 225))

    if surface.screen == "settings":
        _draw_rectangle(rows, 80, 192, 440, 230, (226, 232, 240))
        _draw_rectangle(rows, 80, 250, 440, 288, (226, 232, 240))
        _draw_rectangle(
            rows,
            472,
            195,
            548,
            227,
            (22, 163, 74) if surface.dark_mode_enabled else (148, 163, 184),
        )
        _draw_rectangle(
            rows,
            472,
            253,
            548,
            285,
            (
                (37, 99, 235)
                if surface.notifications_enabled
                else (148, 163, 184)
            ),
        )
    else:
        _draw_rectangle(rows, 80, 192, 548, 230, (226, 232, 240))

    scanlines = b"".join(b"\x00" + bytes(row) for row in rows)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(scanlines, level=9))
        + _png_chunk(b"IEND", b"")
    )


def run_demo(output_root: str | Path, *, correct: bool = False) -> Path:
    """Run the deterministic demo and return its generated report path."""

    surface = DesktopSurface()
    target = "dark-mode-toggle" if correct else "notifications-toggle"
    tools = DesktopTools(surface)
    observed = observe_agent(
        DemoAgent(tools, click_target=target),
        tools,
        output_root,
        tools_attribute="tools",
        capture_screenshot=lambda path: path.write_bytes(
            _render_surface(surface)
        ),
        observe_state=surface.state,
        final_state_verifier=_verify,
    )
    observed.run()
    if observed.last_report_path is None:
        raise RuntimeError("the demo did not create a report")
    return observed.last_report_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a no-dependency desktop-style agent demo."
    )
    parser.add_argument(
        "--correct",
        action="store_true",
        help="click the expected dark-mode setting instead of the wrong one",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("trace") / "generic-agent",
        help="directory where the local trace is written",
    )
    parser.add_argument(
        "--open-report",
        action="store_true",
        help="open the generated report in the default browser",
    )
    args = parser.parse_args()

    try:
        report_path = run_demo(args.output, correct=args.correct)
    except Exception as error:
        print(f"Demo failed before producing a report: {type(error).__name__}")
        return 2

    session = read_session_json(report_path.parent / "session.json")
    verification = session.verification
    task_result = (
        "passed"
        if verification is not None and verification.passed
        else "failed or unverified"
    )
    print(f"Task result: {task_result}")
    print(f"Recorded actions: {session.action_count}")
    print(f"Report: {report_path.resolve()}")

    if args.open_report:
        if not webbrowser.open(report_path.resolve().as_uri(), new=2):
            print("Report could not be opened automatically; use the path above.")

    return 0 if verification is not None and verification.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
