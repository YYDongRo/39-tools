from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_devtools.browser_use import (
    BrowserUseFinalStateCheck,
    observe_browser_use_agent,
)
from agent_devtools.verification import VerificationResult


class _Settings:
    max_actions_per_step = 5


class _State:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.title = ""
        self.screenshot = None
        self.browser_errors: list[str] = []


class _BrowserSession:
    def __init__(self) -> None:
        self.state = _State()

    async def get_browser_state_summary(self) -> _State:
        return self.state


class _ClosingBrowserSession(_BrowserSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def get_browser_state_summary(self) -> _State:
        self.calls += 1
        if self.calls > 1:
            raise ValueError("browser session already closed")
        return self.state


class _Action:
    def model_dump(self, *, exclude_none: bool) -> dict[str, object]:
        return {"navigate": {"url": "https://example.com"}}


class _ModelOutput:
    action = [_Action()]


class _Result:
    error = None
    success = True


class _HistoryItem:
    result = [_Result()]


class _History:
    def __init__(self, verdict: bool) -> None:
        self.verdict = verdict
        self.history = [_HistoryItem()]

    def judgement(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "reasoning": "The judge result.",
            "failure_reason": "The judge failed." if not self.verdict else None,
        }


class _Agent:
    def __init__(self, verdict: bool = True) -> None:
        self.register_new_step_callback = None
        self.directly_open_url = True
        self.initial_url = None
        self.initial_actions = None
        self.settings = _Settings()
        self.browser_session = _BrowserSession()
        self.history = _History(verdict)

    async def run(self, *, on_step_end: object, max_steps: int = 3) -> _History:
        callback = self.register_new_step_callback
        assert callable(callback)
        await callback(self.browser_session.state, _ModelOutput(), 1)
        self.browser_session.state.url = "https://example.com"
        self.browser_session.state.title = "Example Domain"
        assert callable(on_step_end)
        await on_step_end(self)
        return self.history


class _AgentWithClosingSession(_Agent):
    def __init__(self) -> None:
        super().__init__()
        self.browser_session = _ClosingBrowserSession()


def test_final_state_check_passes_url_and_title() -> None:
    check = BrowserUseFinalStateCheck(
        url_contains="/products/wireless-headphones",
        title_contains="Wireless Headphones",
    )

    result = check(
        {
            "url": "https://shop.example.test/products/wireless-headphones",
            "title": "Wireless Headphones | Shop",
        }
    )

    assert result.passed is True
    assert len(result.evidence["checks"]) == 2  # type: ignore[arg-type]


def test_final_state_check_reports_the_failed_check() -> None:
    check = BrowserUseFinalStateCheck(title_contains="Wireless Headphones")

    result = check({"url": "https://shop.example.test/products/usb-c-cable"})

    assert result.passed is False
    assert "title contains 'Wireless Headphones'" in (
        result.failure_reason or ""
    )


def test_final_state_check_requires_a_bound(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one"):
        BrowserUseFinalStateCheck()

    async def run() -> None:
        raw_agent = _Agent(verdict=False)
        observed = observe_browser_use_agent(
            raw_agent,
            "Open example.com",
            tmp_path,
            final_check=BrowserUseFinalStateCheck(
                url_contains="example.com",
                title_contains="Example Domain",
            ),
            print_summary=False,
        )

        await observed.run()

        assert observed.last_session is not None
        verification = observed.last_session.verification
        assert isinstance(verification, VerificationResult)
        assert verification.passed is True
        assert observed.last_session.verification_source == (
            "browser-use:deterministic"
        )
        judge = verification.evidence["browser_use_judge"]
        assert isinstance(judge, dict)
        assert judge["passed"] is False
        report = (observed.last_report_path or Path()).read_text()
        assert "Deterministic final checks" in report

    asyncio.run(run())


def test_deterministic_failure_overrides_a_passing_judge(tmp_path: Path) -> None:
    async def run() -> None:
        observed = observe_browser_use_agent(
            _Agent(),
            "Open example.com",
            tmp_path,
            final_check=BrowserUseFinalStateCheck(
                title_contains="Wrong title",
            ),
            print_summary=False,
        )

        await observed.run()

        assert observed.last_session is not None
        assert observed.last_session.verification is not None
        assert observed.last_session.verification.passed is False
        assert observed.last_session.outcome.value == "failure"

    asyncio.run(run())


def test_final_check_uses_last_observed_state_after_session_closes(
    tmp_path: Path,
) -> None:
    async def run() -> None:
        observed = observe_browser_use_agent(
            _AgentWithClosingSession(),
            "Open example.com",
            tmp_path,
            final_check=BrowserUseFinalStateCheck(
                url_contains="example.com",
                title_contains="Example Domain",
            ),
            print_summary=False,
        )

        await observed.run()

        assert observed.last_session is not None
        assert observed.last_session.verification is not None
        assert observed.last_session.verification.passed is True

    asyncio.run(run())
