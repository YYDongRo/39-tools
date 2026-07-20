from collections.abc import Callable
from pathlib import Path

from agent_devtools.action import ActionRecord
from agent_devtools.recorder import record_action
from agent_devtools.report import write_session_html
from agent_devtools.serialization import write_session_json
from agent_devtools.session import ActionSession


class SessionRecorder:
    def __init__(
        self,
        output_dir: Path,
        capture_screenshot: Callable[[Path], None] | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.capture_screenshot = capture_screenshot
        self.session = ActionSession()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        action_type: str,
        arguments: dict[str, object],
        operation: Callable[[], object],
    ) -> ActionRecord:
        screenshot_before: Path | None = None
        screenshot_after: Path | None = None

        if self.capture_screenshot is not None:
            action_dir = Path("actions") / f"{self.session.action_count + 1:03d}"
            (self.output_dir / action_dir).mkdir(parents=True, exist_ok=True)
            screenshot_before = action_dir / "before.png"
            screenshot_after = action_dir / "after.png"
            self.capture_screenshot(self.output_dir / screenshot_before)

        action = record_action(
            action_type=action_type,
            arguments=arguments,
            operation=operation,
            screenshot_before=screenshot_before,
            screenshot_after=screenshot_after,
        )

        if self.capture_screenshot is not None and screenshot_after is not None:
            try:
                self.capture_screenshot(self.output_dir / screenshot_after)
            except Exception:
                action.screenshot_after = None
                self._append_and_persist(action)
                raise

        self._append_and_persist(action)
        return action

    def _append_and_persist(self, action: ActionRecord) -> None:
        self.session.actions.append(action)
        write_session_json(self.session, self.output_dir / "session.json")
        write_session_html(self.session, self.output_dir / "report.html")
