import agent_devtools
import agent_devtools.playwright as public_playwright
from agent_devtools.action import ActionOutcome, ActionRecord, ActionStatus
from agent_devtools.async_tool_recorder import (
    RecordedAsyncTools,
    record_async_tools,
)
from agent_devtools.failure import FailureCategory
from agent_devtools.integrations.playwright import (
    InputValueExpectation,
    PlaywrightAction,
    RecordedPlaywrightExecutor,
    TextExpectation,
    VisibilityExpectation,
    observe_playwright_page,
    record_playwright_tools,
)
from agent_devtools.serialization import read_action_json, read_session_json
from agent_devtools.session import ActionSession
from agent_devtools.session_recorder import SessionRecorder
from agent_devtools.tool_recorder import RecordedTools, record_tools
from agent_devtools.verification import VerificationResult


def test_core_public_api_exports_supported_types() -> None:
    expected_exports = {
        "ActionOutcome": ActionOutcome,
        "ActionRecord": ActionRecord,
        "ActionSession": ActionSession,
        "ActionStatus": ActionStatus,
        "FailureCategory": FailureCategory,
        "RecordedAsyncTools": RecordedAsyncTools,
        "RecordedTools": RecordedTools,
        "SessionRecorder": SessionRecorder,
        "VerificationResult": VerificationResult,
        "read_action_json": read_action_json,
        "read_session_json": read_session_json,
        "record_async_tools": record_async_tools,
        "record_tools": record_tools,
    }

    assert set(agent_devtools.__all__) == set(expected_exports)
    for name, implementation in expected_exports.items():
        assert getattr(agent_devtools, name) is implementation


def test_playwright_public_api_exports_supported_types() -> None:
    expected_exports = {
        "InputValueExpectation": InputValueExpectation,
        "PlaywrightAction": PlaywrightAction,
        "RecordedPlaywrightExecutor": RecordedPlaywrightExecutor,
        "TextExpectation": TextExpectation,
        "VisibilityExpectation": VisibilityExpectation,
        "observe_playwright_page": observe_playwright_page,
        "record_playwright_tools": record_playwright_tools,
    }

    assert set(public_playwright.__all__) == set(expected_exports)
    for name, implementation in expected_exports.items():
        assert getattr(public_playwright, name) is implementation
