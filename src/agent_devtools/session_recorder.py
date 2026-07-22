from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Self

from agent_devtools.action import ActionRecord
from agent_devtools.recorder import record_action
from agent_devtools.report import write_session_html
from agent_devtools.serialization import read_session_json, write_session_json
from agent_devtools.session import ActionSession
from agent_devtools.verification import VerificationResult


class SessionRecorder:
    def __init__(
        self,
        output_dir: Path,
        capture_screenshot: Callable[[Path], None] | None = None,
        *,
        goal: str | None = None,
        task_verification: Callable[[], VerificationResult] | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.capture_screenshot = capture_screenshot
        self.session = ActionSession(goal=goal)
        self.task_verification = task_verification

        if task_verification is not None and goal is None:
            raise ValueError("automatic task verification requires a goal")

        if self.output_dir.exists() and any(self.output_dir.iterdir()):
            raise FileExistsError(
                f"session output directory is not empty: {self.output_dir}"
            )
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def resume(
        cls,
        output_dir: Path,
        capture_screenshot: Callable[[Path], None] | None = None,
        *,
        task_verification: Callable[[], VerificationResult] | None = None,
    ) -> Self:
        session = read_session_json(output_dir / "session.json")
        if task_verification is not None and session.goal is None:
            raise ValueError("automatic task verification requires a goal")
        recorder = cls.__new__(cls)
        recorder.output_dir = output_dir
        recorder.capture_screenshot = capture_screenshot
        recorder.session = session
        recorder.task_verification = task_verification
        return recorder

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._persist()
        if (
            exception_type is None
            and self.task_verification is not None
            and self.session.verification is None
        ):
            self.verify_task(self.task_verification)

    def record(
        self,
        action_type: str,
        arguments: dict[str, object],
        operation: Callable[[], object],
        *,
        verification: Callable[[], VerificationResult] | None = None,
    ) -> ActionRecord:
        screenshot_before: Path | None = None
        screenshot_after: Path | None = None

        if self.capture_screenshot is not None:
            action_dir = Path("actions") / f"{self.session.action_count + 1:03d}"
            (self.output_dir / action_dir).mkdir(parents=True, exist_ok=False)
            screenshot_before = action_dir / "before.png"
            screenshot_after = action_dir / "after.png"
            self.capture_screenshot(self.output_dir / screenshot_before)

        action = record_action(
            action_type=action_type,
            arguments=arguments,
            operation=operation,
            screenshot_before=screenshot_before,
            screenshot_after=screenshot_after,
            verification=verification,
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

    def verify_task(
        self,
        verification: Callable[[], VerificationResult],
    ) -> VerificationResult:
        if self.session.goal is None:
            raise ValueError("task verification requires a session goal")

        result = verification()
        if not isinstance(result, VerificationResult):
            raise TypeError("verification must return a VerificationResult")

        self.session.verification = result
        self._persist()
        return result

    def _append_and_persist(self, action: ActionRecord) -> None:
        self.session.verification = None
        self.session.actions.append(action)
        self._persist()

    def _persist(self) -> None:
        write_session_json(self.session, self.output_dir / "session.json")
        write_session_html(self.session, self.output_dir / "report.html")
