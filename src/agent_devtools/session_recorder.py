from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.recorder import record_action
from agent_devtools.report import write_session_html
from agent_devtools.runtime import RuntimeContext, collect_runtime_context
from agent_devtools.serialization import read_session_json, write_session_json
from agent_devtools.run_state import _RunStateReporter
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
        run_context: RuntimeContext | None = None,
        run_state_path: str | Path | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.capture_screenshot = capture_screenshot
        self.session = ActionSession(
            goal=goal,
            run_context=(
                run_context
                if run_context is not None
                else collect_runtime_context()
            ),
        )
        self.task_verification = task_verification
        self._run_state = None

        if task_verification is not None and goal is None:
            raise ValueError("automatic task verification requires a goal")

        if self.output_dir.exists() and any(self.output_dir.iterdir()):
            raise FileExistsError(
                f"session output directory is not empty: {self.output_dir}"
            )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if run_state_path is not None:
            self._run_state = _RunStateReporter(
                run_state_path,
                self.output_dir,
                goal,
                started_at=datetime.now(UTC),
            )

    @classmethod
    def resume(
        cls,
        output_dir: Path,
        capture_screenshot: Callable[[Path], None] | None = None,
        *,
        task_verification: Callable[[], VerificationResult] | None = None,
        run_state_path: str | Path | None = None,
    ) -> Self:
        session = read_session_json(output_dir / "session.json")
        if task_verification is not None and session.goal is None:
            raise ValueError("automatic task verification requires a goal")
        recorder = cls.__new__(cls)
        recorder.output_dir = output_dir
        recorder.capture_screenshot = capture_screenshot
        recorder.session = session
        recorder.task_verification = task_verification
        recorder._run_state = (
            _RunStateReporter(
                run_state_path,
                output_dir,
                session.goal,
                started_at=(
                    session.actions[0].start_time
                    if session.actions
                    else datetime.now(UTC)
                ),
            )
            if run_state_path is not None
            else None
        )
        return recorder

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            self._persist()
            if (
                exception_type is None
                and self.task_verification is not None
                and self.session.verification is None
            ):
                self.verify_task(self.task_verification)
        except BaseException as error:
            if self._run_state is not None:
                self._run_state.finish(self.session, exception=error)
            raise
        else:
            if self._run_state is not None:
                if exception_type is None:
                    self._run_state.finish(self.session)
                else:
                    self._run_state.finish(
                        self.session,
                        error_type=exception_type.__name__,
                    )

    def record(
        self,
        action_type: str,
        arguments: dict[str, object],
        operation: Callable[[], object],
        *,
        observations: dict[str, object] | None = None,
        finalize_observations: Callable[[], None] | None = None,
        verification: Callable[[], VerificationResult] | None = None,
        failure_diagnosis: Callable[[ActionRecord], ActionRecord] | None = None,
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
            observations=observations,
            finalize_observations=finalize_observations,
            verification=verification,
        )
        if (
            action.status is ActionStatus.FAILURE
            and failure_diagnosis is not None
        ):
            action = failure_diagnosis(action)
            if not isinstance(action, ActionRecord):
                raise TypeError(
                    "failure_diagnosis must return an ActionRecord"
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
        if self._run_state is not None:
            self._run_state.update_action_count(
                self.session.action_count,
                self.session.actions[-1].action_type
                if self.session.actions
                else None,
            )
