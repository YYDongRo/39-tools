import agent_devtools
import agent_devtools.browser_use as public_browser_use
import agent_devtools.playwright as public_playwright
from agent_devtools.agent import (
    ObservedAgent,
    ObservedAsyncAgent,
    observe_agent,
    observe_async_agent,
)
from agent_devtools.action import ActionOutcome, ActionRecord, ActionStatus
from agent_devtools.analysis import TrajectoryFinding, analyze_session
from agent_devtools.async_tool_recorder import (
    RecordedAsyncTools,
    record_async_tools,
)
from agent_devtools.config import AgentDevToolsConfig
from agent_devtools.failure import FailureCategory
from agent_devtools.final_state import FinalStateObservation
from agent_devtools.evaluation import (
    AgentEvaluation,
    EvaluationComparison,
    EvaluationComparisonStatus,
    EvaluationRunStatus,
    EvaluationStatusCounts,
)
from agent_devtools.evaluation_comparison import compare_evaluations
from agent_devtools.integrations.browser_use import (
    BrowserUseFinalCheck,
    BrowserUseFinalStateCheck,
    BrowserUsePreflightCheck,
    BrowserUsePreflightResult,
    ObservedBrowserUseAgent,
    observe_browser_use_agent,
)
from agent_devtools.integrations.browser_use_evaluation import (
    evaluate_browser_use_agent,
)
from agent_devtools.integrations.playwright import (
    evaluate_playwright_session_replay,
    InputValueExpectation,
    PlaywrightAction,
    PlaywrightReplayStabilityResult,
    RecordedPlaywrightExecutor,
    PlaywrightSessionReplayResult,
    ReplayStabilityStatus,
    TextExpectation,
    VisibilityExpectation,
    observe_async_playwright_page,
    observe_playwright_page,
    record_async_playwright_tools,
    record_playwright_tools,
    replay_playwright_session_action,
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
from agent_devtools.integrations.gemini_final_state import (
    AsyncGeminiFinalStateVerifier,
    GeminiFinalStateVerifier,
    async_gemini_final_state_verifier,
    gemini_final_state_verifier,
)
from agent_devtools.integrations.playwright_expectation_generation import (
    GeneratedTaskExpectation,
)
from agent_devtools.integrations.playwright_final_state import (
    AsyncFinalStateVerifier,
    FinalPageState,
    FinalStateAssessment,
    FinalStateVerifier,
    observe_final_async_playwright_state,
    observe_final_playwright_state,
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
from agent_devtools.replay import ReplayResult, replay_click, replay_fill
from agent_devtools.serialization import read_action_json, read_session_json
from agent_devtools.session import ActionSession
from agent_devtools.session_recorder import SessionRecorder
from agent_devtools.tool_recorder import RecordedTools, record_tools
from agent_devtools.trajectory import TrajectoryVerificationResult
from agent_devtools.verification import VerificationResult
from agent_devtools.integrations.trajectory_judge import (
    AsyncGeminiTrajectoryJudge,
    AsyncOpenAITrajectoryJudge,
    GeminiTrajectoryJudge,
    OpenAITrajectoryJudge,
    async_trajectory_judge_from_env,
    trajectory_judge_from_env,
)


def test_core_public_api_exports_supported_types() -> None:
    expected_exports = {
        "ActionOutcome": ActionOutcome,
        "ActionRecord": ActionRecord,
        "ActionSession": ActionSession,
        "ActionStatus": ActionStatus,
        "AgentDevToolsConfig": AgentDevToolsConfig,
        "EvaluationComparison": EvaluationComparison,
        "EvaluationComparisonStatus": EvaluationComparisonStatus,
        "EvaluationStatusCounts": EvaluationStatusCounts,
        "FailureCategory": FailureCategory,
        "FinalStateObservation": FinalStateObservation,
        "ObservedAgent": ObservedAgent,
        "ObservedAsyncAgent": ObservedAsyncAgent,
        "RecordedAsyncTools": RecordedAsyncTools,
        "RecordedTools": RecordedTools,
        "ReplayResult": ReplayResult,
        "SessionRecorder": SessionRecorder,
        "TrajectoryFinding": TrajectoryFinding,
        "TrajectoryVerificationResult": TrajectoryVerificationResult,
        "VerificationResult": VerificationResult,
        "AsyncGeminiTrajectoryJudge": AsyncGeminiTrajectoryJudge,
        "AsyncOpenAITrajectoryJudge": AsyncOpenAITrajectoryJudge,
        "GeminiTrajectoryJudge": GeminiTrajectoryJudge,
        "OpenAITrajectoryJudge": OpenAITrajectoryJudge,
        "async_trajectory_judge_from_env": async_trajectory_judge_from_env,
        "trajectory_judge_from_env": trajectory_judge_from_env,
        "analyze_session": analyze_session,
        "compare_evaluations": compare_evaluations,
        "read_action_json": read_action_json,
        "read_session_json": read_session_json,
        "observe_agent": observe_agent,
        "observe_async_agent": observe_async_agent,
        "record_async_tools": record_async_tools,
        "record_tools": record_tools,
        "replay_click": replay_click,
        "replay_fill": replay_fill,
    }

    assert set(agent_devtools.__all__) == set(expected_exports)
    for name, implementation in expected_exports.items():
        assert getattr(agent_devtools, name) is implementation


def test_playwright_public_api_exports_supported_types() -> None:
    expected_exports = {
        "AllOf": AllOf,
        "AsyncExpectationGenerator": AsyncExpectationGenerator,
        "AsyncFinalStateVerifier": AsyncFinalStateVerifier,
        "AsyncGeminiFinalStateVerifier": AsyncGeminiFinalStateVerifier,
        "AsyncGeminiExpectationGenerator": AsyncGeminiExpectationGenerator,
        "AsyncOpenAIExpectationGenerator": AsyncOpenAIExpectationGenerator,
        "DEFAULT_OPENAI_MODEL": DEFAULT_OPENAI_MODEL,
        "DEFAULT_GEMINI_MODEL": DEFAULT_GEMINI_MODEL,
        "ElementVisible": ElementVisible,
        "ExpectationGenerator": ExpectationGenerator,
        "FinalPageState": FinalPageState,
        "FinalStateAssessment": FinalStateAssessment,
        "FinalStateVerifier": FinalStateVerifier,
        "GeneratedTaskExpectation": GeneratedTaskExpectation,
        "GeminiExpectationGenerator": GeminiExpectationGenerator,
        "GeminiFinalStateVerifier": GeminiFinalStateVerifier,
        "GeminiToolAgent": GeminiToolAgent,
        "GeminiToolDefinition": GeminiToolDefinition,
        "InputValueExpectation": InputValueExpectation,
        "ObservedAsyncPlaywrightAgent": ObservedAsyncPlaywrightAgent,
        "ObservedPlaywrightAgent": ObservedPlaywrightAgent,
        "OpenAIExpectationGenerator": OpenAIExpectationGenerator,
        "PlaywrightAction": PlaywrightAction,
        "PlaywrightReplayStabilityResult": PlaywrightReplayStabilityResult,
        "PlaywrightSessionReplayResult": PlaywrightSessionReplayResult,
        "PropertyEquals": PropertyEquals,
        "RecordedPlaywrightExecutor": RecordedPlaywrightExecutor,
        "ReplayStabilityStatus": ReplayStabilityStatus,
        "TaskExpectation": TaskExpectation,
        "TextMatch": TextMatch,
        "TextExpectation": TextExpectation,
        "UrlMatch": UrlMatch,
        "VisibilityExpectation": VisibilityExpectation,
        "all_of": all_of,
        "async_openai_expectations": async_openai_expectations,
        "async_gemini_expectations": async_gemini_expectations,
        "async_gemini_final_state_verifier": async_gemini_final_state_verifier,
        "element_visible": element_visible,
        "observe_async_playwright_agent": observe_async_playwright_agent,
        "observe_async_playwright_page": observe_async_playwright_page,
        "observe_final_async_playwright_state": observe_final_async_playwright_state,
        "observe_final_playwright_state": observe_final_playwright_state,
        "observe_playwright_agent": observe_playwright_agent,
        "observe_playwright_page": observe_playwright_page,
        "openai_expectations": openai_expectations,
        "gemini_expectations": gemini_expectations,
        "gemini_final_state_verifier": gemini_final_state_verifier,
        "property_equals": property_equals,
        "record_async_playwright_tools": record_async_playwright_tools,
        "record_playwright_tools": record_playwright_tools,
        "evaluate_playwright_session_replay": evaluate_playwright_session_replay,
        "replay_playwright_session_action": replay_playwright_session_action,
        "text_contains": text_contains,
        "text_equals": text_equals,
        "url_matches": url_matches,
    }

    assert set(public_playwright.__all__) == set(expected_exports)
    for name, implementation in expected_exports.items():
        assert getattr(public_playwright, name) is implementation


def test_browser_use_public_api_exports_supported_types() -> None:
    expected_exports = {
        "AgentEvaluation": AgentEvaluation,
        "AgentDevToolsConfig": AgentDevToolsConfig,
        "BrowserUseFinalCheck": BrowserUseFinalCheck,
        "BrowserUseFinalStateCheck": BrowserUseFinalStateCheck,
        "BrowserUsePreflightCheck": BrowserUsePreflightCheck,
        "BrowserUsePreflightResult": BrowserUsePreflightResult,
        "EvaluationRunStatus": EvaluationRunStatus,
        "EvaluationComparison": EvaluationComparison,
        "EvaluationComparisonStatus": EvaluationComparisonStatus,
        "ObservedBrowserUseAgent": ObservedBrowserUseAgent,
        "compare_evaluations": compare_evaluations,
        "evaluate_browser_use_agent": evaluate_browser_use_agent,
        "observe_browser_use_agent": observe_browser_use_agent,
    }

    assert set(public_browser_use.__all__) == set(expected_exports)
    for name, implementation in expected_exports.items():
        assert getattr(public_browser_use, name) is implementation
