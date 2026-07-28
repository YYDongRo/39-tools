from __future__ import annotations

import json

import pytest

from agent_devtools.integrations.gemini_agent import (
    GeminiToolAgent,
    GeminiToolDefinition,
)


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
    def __init__(self, steps: list[Step], output_text: str = "") -> None:
        self.steps = steps
        self.output_text = output_text


class Interactions:
    def __init__(self, responses: list[Response]) -> None:
        self.responses = iter(responses)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> Response:
        self.calls.append(kwargs)
        return next(self.responses)


class Client:
    def __init__(self, responses: list[Response]) -> None:
        self.interactions = Interactions(responses)


class Tools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def observe(self) -> dict[str, object]:
        self.calls.append(("observe", None))
        return {"url": "about:blank"}

    def navigate(self, url: str) -> dict[str, object]:
        self.calls.append(("navigate", url))
        return {"url": url}


TOOL_DEFINITIONS = (
    GeminiToolDefinition(
        "observe",
        "Read the current browser state.",
        {"type": "object", "properties": {}, "additionalProperties": False},
    ),
    GeminiToolDefinition(
        "navigate",
        "Open a URL.",
        {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
            "additionalProperties": False,
        },
    ),
)


def test_gemini_agent_runs_tool_calls_and_sends_full_stateless_history() -> None:
    client = Client(
        [
            Response(
                [
                    Step(
                        "function_call",
                        name="observe",
                        call_id="call-1",
                        arguments={},
                    )
                ]
            ),
            Response(
                [
                    Step(
                        "function_call",
                        name="navigate",
                        call_id="call-2",
                        arguments={"url": "https://example.com"},
                    )
                ]
            ),
            Response(
                [Step("model_output", text="Done")],
                output_text="Done",
            ),
        ]
    )
    tools = Tools()
    agent = GeminiToolAgent(
        TOOL_DEFINITIONS,
        model="gemini-test",
        system_instruction="Complete the browser task.",
        client=client,
    )

    result = agent.run("Open example.com", tools=tools)

    assert result == "Done"
    assert tools.calls == [
        ("observe", None),
        ("navigate", "https://example.com"),
    ]
    assert all(call["store"] is False for call in client.interactions.calls)
    first_history = client.interactions.calls[0]["input"]
    assert first_history == [
        {
            "type": "user_input",
            "content": [{"type": "text", "text": "Open example.com"}],
        }
    ]
    second_history = client.interactions.calls[1]["input"]
    assert len(second_history) == 3  # type: ignore[arg-type]
    result_step = second_history[-1]  # type: ignore[index]
    assert result_step["type"] == "function_result"
    assert result_step["is_error"] is False
    assert json.loads(result_step["result"][0]["text"]) == {  # type: ignore[index]
        "ok": True,
        "result": {"url": "about:blank"},
    }


def test_gemini_agent_returns_tool_errors_to_the_model() -> None:
    class FailingTools(Tools):
        def navigate(self, url: str) -> dict[str, object]:
            raise RuntimeError("navigation failed")

    client = Client(
        [
            Response(
                [
                    Step(
                        "function_call",
                        name="navigate",
                        call_id="call-1",
                        arguments={"url": "https://example.com"},
                    )
                ]
            ),
            Response([Step("model_output", text="Stopped")], "Stopped"),
        ]
    )
    agent = GeminiToolAgent(
        TOOL_DEFINITIONS,
        model="gemini-test",
        system_instruction="Complete the browser task.",
        client=client,
    )

    assert agent.run("Open example.com", tools=FailingTools()) == "Stopped"

    result_step = client.interactions.calls[1]["input"][-1]  # type: ignore[index]
    payload = json.loads(result_step["result"][0]["text"])
    assert result_step["is_error"] is True
    assert payload == {
        "ok": False,
        "error_type": "RuntimeError",
        "message": "navigation failed",
    }


def test_gemini_agent_stops_after_the_configured_turn_limit() -> None:
    response = Response(
        [
            Step(
                "function_call",
                name="observe",
                call_id="call-1",
                arguments={},
            )
        ]
    )
    agent = GeminiToolAgent(
        TOOL_DEFINITIONS,
        model="gemini-test",
        system_instruction="Complete the browser task.",
        max_turns=1,
        client=Client([response]),
    )

    with pytest.raises(RuntimeError, match="did not finish within 1 turns"):
        agent.run("Open example.com", tools=Tools())
