from __future__ import annotations

import json
import importlib.util
from pathlib import Path

from playwright.sync_api import sync_playwright

from agent_devtools.action import ActionOutcome
from agent_devtools.integrations.gemini_agent import GeminiToolAgent
from agent_devtools.integrations.gemini_final_state import (
    GeminiFinalStateVerifier,
)
from agent_devtools.playwright import observe_playwright_agent


_EXAMPLE_PATH = (
    Path(__file__).resolve().parents[2] / "examples" / "gemini_browser_agent.py"
)
_EXAMPLE_SPEC = importlib.util.spec_from_file_location(
    "gemini_browser_agent_example",
    _EXAMPLE_PATH,
)
if _EXAMPLE_SPEC is None or _EXAMPLE_SPEC.loader is None:
    raise RuntimeError("could not load the Gemini browser example")
_EXAMPLE = importlib.util.module_from_spec(_EXAMPLE_SPEC)
_EXAMPLE_SPEC.loader.exec_module(_EXAMPLE)
START_URL = _EXAMPLE.START_URL
BrowserTools = _EXAMPLE.BrowserTools
tool_definitions = _EXAMPLE.tool_definitions


class Step:
    def __init__(
        self,
        step_type: str,
        *,
        name: str | None = None,
        call_id: str | None = None,
        arguments: dict[str, object] | None = None,
        text: str | None = None,
    ) -> None:
        self.type = step_type
        self.name = name
        self.id = call_id
        self.arguments = arguments
        self.text = text

    def model_dump(self) -> dict[str, object]:
        if self.type == "function_call":
            return {
                "type": self.type,
                "name": self.name,
                "id": self.id,
                "arguments": self.arguments,
            }
        return {
            "type": self.type,
            "content": [{"type": "text", "text": self.text}],
        }


class Response:
    def __init__(
        self,
        *,
        output_text: str = "",
        steps: list[Step] | None = None,
    ) -> None:
        self.output_text = output_text
        self.steps = [] if steps is None else steps


class Interactions:
    def __init__(self, responses: list[Response]) -> None:
        self.responses = iter(responses)

    def create(self, **kwargs: object) -> Response:
        return next(self.responses)


class Client:
    def __init__(self, responses: list[Response]) -> None:
        self.interactions = Interactions(responses)


def _assessment_response() -> Response:
    return Response(
        output_text=json.dumps(
            {
                "verdict": "passed",
                "summary": "The requested product page is open.",
                "evidence": [
                    "The final page heading is Wireless Headphones."
                ],
            }
        )
    )


def _function_call(
    name: str,
    call_id: str,
    arguments: dict[str, object],
) -> Response:
    return Response(
        steps=[
            Step(
                "function_call",
                name=name,
                call_id=call_id,
                arguments=arguments,
            )
        ]
    )


def test_fake_gemini_drives_a_recorded_browser_task(tmp_path: Path) -> None:
    client = Client(
        [
            _function_call("navigate", "1", {"url": START_URL}),
            _function_call(
                "fill",
                "2",
                {"selector": "#search", "text": "Wireless Headphones"},
            ),
            _function_call("click", "3", {"selector": "#search-button"}),
            _function_call("click", "4", {"selector": "#headphones-result"}),
            Response(
                output_text="Opened the product.",
                steps=[Step("model_output", text="Opened the product.")],
            ),
            _assessment_response(),
        ]
    )
    agent = GeminiToolAgent(
        tool_definitions(),
        model="gemini-test",
        system_instruction="Complete the local browser task.",
        client=client,
    )
    verifier = GeminiFinalStateVerifier(
        model="gemini-test",
        client=client,
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        observed = observe_playwright_agent(
            agent,
            BrowserTools(page, START_URL),
            page,
            tmp_path,
            final_state_verifier=verifier,
            methods=("navigate", "fill", "click"),
        )

        result = observed.run("Open the Wireless Headphones product")
        browser.close()

    assert result == "Opened the product."
    assert observed.last_trace is not None
    assert observed.last_trace.session.action_count == 4
    assert observed.last_trace.session.outcome is ActionOutcome.SUCCESS
    assert observed.last_trace.session.verification_source == (
        "gemini:gemini-test:final-state"
    )
    assert observed.last_report_path is not None
    assert observed.last_report_path.is_file()
    report = observed.last_report_path.read_text(encoding="utf-8")
    assert "AI task assessment" in report
    assert "The final page heading is Wireless Headphones." in report
