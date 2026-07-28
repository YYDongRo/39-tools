import agent_devtools
import agent_devtools.playwright as public_playwright
from agent_devtools.action import ActionOutcome, ActionRecord, ActionStatus
from agent_devtools.analysis import TrajectoryFinding, analyze_session
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
    observe_async_playwright_page,
    observe_playwright_page,
    record_async_playwright_tools,
    record_playwright_tools,
)
from agent_devtools.integrations.playwright_agent import (
    AsyncExpectationGenerator,
    ExpectationGenerator,
    ObservedAsyncPlaywrightAgent,
    ObservedPlaywrightAgent,
    observe_async_playwright_agent,
    observe_playwright_agent,
)
from agent_devtools.integrations.openai_expectations import (
    AsyncOpenAIExpectationGenerator,
    DEFAULT_OPENAI_MODEL,
    OpenAIExpectationGenerator,
    async_openai_expectations,
    openai_expectations,
)
from agent_devtools.integrations.gemini_agent import (
    GeminiToolAgent,
    GeminiToolDefinition,
)
from agent_devtools.integrations.gemini_expectations import (
    AsyncGeminiExpectationGenerator,
    DEFAULT_GEMINI_MODEL,
    GeminiExpectationGenerator,
    async_gemini_expectations,
    gemini_expectations,
)
from agent_devtools.integrations.playwright_expectation_generation import (
    GeneratedTaskExpectation,
)
from agent_devtools.integrations.playwright_task import (
    AllOf,
    ElementVisible,
    PropertyEquals,
    TaskExpectation,
    TextMatch,
    UrlMatch,
    all_of,
    element_visible,
    property_equals,
    text_contains,
    text_equals,
    url_matches,
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
        "TrajectoryFinding": TrajectoryFinding,
        "VerificationResult": VerificationResult,
        "analyze_session": analyze_session,
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
        "AllOf": AllOf,
        "AsyncExpectationGenerator": AsyncExpectationGenerator,
        "AsyncGeminiExpectationGenerator": AsyncGeminiExpectationGenerator,
        "AsyncOpenAIExpectationGenerator": AsyncOpenAIExpectationGenerator,
        "DEFAULT_OPENAI_MODEL": DEFAULT_OPENAI_MODEL,
        "DEFAULT_GEMINI_MODEL": DEFAULT_GEMINI_MODEL,
        "ElementVisible": ElementVisible,
        "ExpectationGenerator": ExpectationGenerator,
        "GeneratedTaskExpectation": GeneratedTaskExpectation,
        "GeminiExpectationGenerator": GeminiExpectationGenerator,
        "GeminiToolAgent": GeminiToolAgent,
        "GeminiToolDefinition": GeminiToolDefinition,
        "InputValueExpectation": InputValueExpectation,
        "ObservedAsyncPlaywrightAgent": ObservedAsyncPlaywrightAgent,
        "ObservedPlaywrightAgent": ObservedPlaywrightAgent,
        "OpenAIExpectationGenerator": OpenAIExpectationGenerator,
        "PlaywrightAction": PlaywrightAction,
        "PropertyEquals": PropertyEquals,
        "RecordedPlaywrightExecutor": RecordedPlaywrightExecutor,
        "TaskExpectation": TaskExpectation,
        "TextMatch": TextMatch,
        "TextExpectation": TextExpectation,
        "UrlMatch": UrlMatch,
        "VisibilityExpectation": VisibilityExpectation,
        "all_of": all_of,
        "async_openai_expectations": async_openai_expectations,
        "async_gemini_expectations": async_gemini_expectations,
        "element_visible": element_visible,
        "observe_async_playwright_agent": observe_async_playwright_agent,
        "observe_async_playwright_page": observe_async_playwright_page,
        "observe_playwright_agent": observe_playwright_agent,
        "observe_playwright_page": observe_playwright_page,
        "openai_expectations": openai_expectations,
        "gemini_expectations": gemini_expectations,
        "property_equals": property_equals,
        "record_async_playwright_tools": record_async_playwright_tools,
        "record_playwright_tools": record_playwright_tools,
        "text_contains": text_contains,
        "text_equals": text_equals,
        "url_matches": url_matches,
    }

    assert set(public_playwright.__all__) == set(expected_exports)
    for name, implementation in expected_exports.items():
        assert getattr(public_playwright, name) is implementation
