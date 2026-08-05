import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_devtools import FinalStateObservation
from agent_devtools.action import ActionRecord, ActionStatus
from agent_devtools.integrations.trajectory_judge import (
    AsyncOpenAITrajectoryJudge,
    GeminiTrajectoryJudge,
    OpenAITrajectoryJudge,
    async_trajectory_judge_from_env,
    trajectory_judge_from_env,
)


def _observation() -> FinalStateObservation:
    return FinalStateObservation(
        task="Open Settings and enable dark mode.",
        state={"screen": "settings", "dark_mode_enabled": True},
        actions=(
            ActionRecord(
                action_type="click",
                arguments={"target": "dark-mode-toggle", "api_key": "sk-" + "a" * 24},
                start_time=datetime(2026, 1, 1, tzinfo=UTC),
                duration_ms=12,
                status=ActionStatus.SUCCESS,
                observations={
                    "state_before": {"dark_mode_enabled": False},
                    "state_after": {"dark_mode_enabled": True},
                },
                screenshot_before=Path("actions/001/before.png"),
                screenshot_after=Path("actions/001/after.png"),
            ),
        ),
        screenshot_path=Path("actions/001/after.png"),
    )


def _payload() -> dict[str, object]:
    return {
        "final": {
            "verdict": "passed",
            "summary": "Settings is open and dark mode is enabled.",
            "evidence": ["The final state reports dark_mode_enabled=true."],
        },
        "actions": [
            {
                "index": 1,
                "verdict": "passed",
                "summary": "The click changed dark mode from false to true.",
                "evidence": ["state_after shows dark_mode_enabled=true."],
            }
        ],
    }


class FakeResponses:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps(self.payload))


class FakeOpenAIClient:
    def __init__(self, payload: object) -> None:
        self.responses = FakeResponses(payload)


class AsyncFakeResponses(FakeResponses):
    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps(self.payload))


class AsyncFakeOpenAIClient:
    def __init__(self, payload: object) -> None:
        self.responses = AsyncFakeResponses(payload)


class FakeGeminiInteractions(FakeResponses):
    pass


class FakeGeminiClient:
    def __init__(self, payload: object) -> None:
        self.interactions = FakeGeminiInteractions(payload)


def test_openai_trajectory_judge_returns_action_and_final_results() -> None:
    client = FakeOpenAIClient(_payload())
    result = OpenAITrajectoryJudge(model="test-model", client=client)(
        _observation()
    )

    assert result.source == "openai:test-model:trajectory"
    assert result.final is not None and result.final.passed
    assert result.actions[0] is not None and result.actions[0].passed
    assert client.responses.calls
    request_text = client.responses.calls[0]["input"]
    assert isinstance(request_text, list)
    assert "[REDACTED]" in request_text[1]["content"]
    assert "sk-aaaaaaaa" not in request_text[1]["content"]
    assert "actions/001/after.png" not in request_text[1]["content"]


def test_gemini_trajectory_judge_uses_structured_response() -> None:
    client = FakeGeminiClient(_payload())
    result = GeminiTrajectoryJudge(model="test-model", client=client)(
        _observation()
    )

    assert result.final is not None and result.final.passed
    assert client.interactions.calls[0]["response_format"]["mime_type"] == (
        "application/json"
    )


def test_async_openai_trajectory_judge_returns_same_result() -> None:
    async def run() -> None:
        client = AsyncFakeOpenAIClient(_payload())
        result = await AsyncOpenAITrajectoryJudge(
            model="test-model",
            client=client,
        )(_observation())
        assert result.final is not None and result.final.passed
        assert result.actions[0] is not None and result.actions[0].passed

    asyncio.run(run())


def test_judge_keeps_unverified_items_unverified() -> None:
    payload = {
        "final": {
            "verdict": "unverified",
            "summary": "The supplied state does not prove completion.",
            "evidence": [],
        },
        "actions": [],
    }
    result = OpenAITrajectoryJudge(
        model="test-model",
        client=FakeOpenAIClient(payload),
    )(_observation())

    assert result.final is None
    assert result.note == "The supplied state does not prove completion."
    assert result.actions == (None,)
    assert result.action_notes == (
        "LLM did not return an assessment for this action.",
    )


def test_judge_rejects_invalid_response() -> None:
    with pytest.raises(ValueError, match="invalid trajectory judgement object"):
        OpenAITrajectoryJudge(
            model="test-model",
            client=FakeOpenAIClient("not-json"),
        )(_observation())


def test_env_factory_selects_one_explicit_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_DEVTOOLS_LLM_PROVIDER", "openai")
    monkeypatch.setenv("AGENT_DEVTOOLS_LLM_MODEL", "configured-model")
    sync_judge = trajectory_judge_from_env()
    async_judge = async_trajectory_judge_from_env()

    assert isinstance(sync_judge, OpenAITrajectoryJudge)
    assert sync_judge.model == "configured-model"
    assert isinstance(async_judge, AsyncOpenAITrajectoryJudge)


def test_env_factory_infers_gemini_from_its_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_DEVTOOLS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    assert isinstance(trajectory_judge_from_env(), GeminiTrajectoryJudge)


def test_env_factory_rejects_ambiguous_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_DEVTOOLS_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")

    with pytest.raises(ValueError, match="more than one provider"):
        trajectory_judge_from_env()
