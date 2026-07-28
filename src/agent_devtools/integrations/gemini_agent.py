from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agent_devtools.integrations.gemini_expectations import DEFAULT_GEMINI_MODEL


@dataclass(frozen=True)
class GeminiToolDefinition:
    name: str
    description: str
    parameters: dict[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("tool name cannot be empty")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("tool description cannot be empty")
        if not isinstance(self.parameters, dict):
            raise TypeError("tool parameters must be a JSON Schema object")

    def as_gemini_tool(self) -> dict[str, object]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class GeminiToolAgent:
    def __init__(
        self,
        tool_definitions: tuple[GeminiToolDefinition, ...],
        *,
        model: str = DEFAULT_GEMINI_MODEL,
        system_instruction: str,
        max_turns: int = 12,
        client: object | None = None,
    ) -> None:
        if not tool_definitions:
            raise ValueError("at least one tool definition is required")
        names = [definition.name for definition in tool_definitions]
        if len(set(names)) != len(names):
            raise ValueError("tool definition names must be unique")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model cannot be empty")
        if not isinstance(system_instruction, str) or not system_instruction.strip():
            raise ValueError("system_instruction cannot be empty")
        if (
            not isinstance(max_turns, int)
            or isinstance(max_turns, bool)
            or max_turns <= 0
        ):
            raise ValueError("max_turns must be a positive integer")

        self.tool_definitions = tool_definitions
        self.model = model
        self.system_instruction = system_instruction
        self.max_turns = max_turns
        self._client = client

    def run(self, user_request: str, *, tools: object) -> str:
        if not isinstance(user_request, str) or not user_request.strip():
            raise ValueError("user_request cannot be empty")

        history: list[dict[str, object]] = [
            {
                "type": "user_input",
                "content": [{"type": "text", "text": user_request}],
            }
        ]
        declarations = [
            definition.as_gemini_tool()
            for definition in self.tool_definitions
        ]
        allowed_tools = {definition.name for definition in self.tool_definitions}

        for _ in range(self.max_turns):
            response = self._get_client().interactions.create(  # type: ignore[attr-defined]
                model=self.model,
                input=list(history),
                system_instruction=self.system_instruction,
                tools=declarations,
                store=False,
            )
            response_steps = getattr(response, "steps", None)
            if not isinstance(response_steps, list):
                raise ValueError("Gemini returned no interaction steps")

            function_calls: list[object] = []
            for step in response_steps:
                history.append(_step_dict(step))
                if getattr(step, "type", None) == "function_call":
                    function_calls.append(step)

            if not function_calls:
                output_text = getattr(response, "output_text", None)
                if isinstance(output_text, str) and output_text.strip():
                    return output_text
                raise ValueError("Gemini finished without a result or tool call")

            for call in function_calls:
                result, is_error = _call_tool(call, tools, allowed_tools)
                history.append(
                    {
                        "type": "function_result",
                        "name": getattr(call, "name"),
                        "call_id": getattr(call, "id"),
                        "result": [
                            {
                                "type": "text",
                                "text": json.dumps(result, ensure_ascii=False),
                            }
                        ],
                        "is_error": is_error,
                    }
                )

        raise RuntimeError(
            f"Gemini agent did not finish within {self.max_turns} turns"
        )

    def _get_client(self) -> object:
        if self._client is None:
            try:
                from google import genai
            except ImportError as error:
                raise ImportError(
                    "Install agent-devtools[llm-gemini] to use the Gemini agent"
                ) from error
            self._client = genai.Client()
        return self._client


def _step_dict(step: object) -> dict[str, object]:
    model_dump = getattr(step, "model_dump", None)
    if not callable(model_dump):
        raise TypeError("Gemini interaction steps must support model_dump()")
    value = model_dump()
    if not isinstance(value, dict):
        raise TypeError("Gemini interaction step must serialize to an object")
    return value


def _call_tool(
    call: object,
    tools: object,
    allowed_tools: set[str],
) -> tuple[object, bool]:
    name = getattr(call, "name", None)
    call_id = getattr(call, "id", None)
    arguments = getattr(call, "arguments", None)
    if not isinstance(name, str) or not name:
        raise ValueError("Gemini returned a function call without a name")
    if not isinstance(call_id, str) or not call_id:
        raise ValueError("Gemini returned a function call without an ID")
    if not isinstance(arguments, dict):
        raise ValueError("Gemini returned invalid function arguments")
    if name not in allowed_tools:
        return {"ok": False, "error_type": "UnknownTool"}, True

    method = getattr(tools, name, None)
    if not callable(method):
        return {"ok": False, "error_type": "UnavailableTool"}, True
    try:
        result = method(**arguments)
    except Exception as error:
        return {
            "ok": False,
            "error_type": type(error).__name__,
            "message": str(error)[:1_000],
        }, True
    return {"ok": True, "result": result}, False


__all__ = [
    "GeminiToolAgent",
    "GeminiToolDefinition",
]
