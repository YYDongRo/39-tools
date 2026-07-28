import asyncio
import json

import pytest

from agent_devtools.integrations.gemini_expectations import (
    AsyncGeminiExpectationGenerator,
    GeminiExpectationGenerator,
)
from agent_devtools.integrations.playwright_task import UrlMatch


class Response:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class Interactions:
    def __init__(self, response: Response) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> Response:
        self.calls.append(kwargs)
        return self.response


class AsyncInteractions(Interactions):
    async def create(self, **kwargs: object) -> Response:
        self.calls.append(kwargs)
        return self.response


class AsyncClient:
    def __init__(self, response: Response) -> None:
        self.interactions = AsyncInteractions(response)


class Client:
    def __init__(self, response: Response) -> None:
        self.interactions = Interactions(response)
        self.aio = AsyncClient(response)


def _response() -> Response:
    return Response(
        json.dumps(
            {
                "inferred_goal": "Open example.com",
                "can_verify": True,
                "reason": None,
                "checks": [
                    {
                        "type": "url_match",
                        "selector": None,
                        "expected_text": None,
                        "host": "example.com",
                        "path_prefix": None,
                        "scheme": "https",
                        "allow_subdomains": False,
                        "property_name": None,
                        "expected_value": None,
                        "timeout_ms": None,
                    }
                ],
            }
        )
    )


def test_gemini_generator_uses_structured_output_without_storing_response() -> None:
    client = Client(_response())
    generator = GeminiExpectationGenerator(
        model="gemini-test",
        application_context="The agent controls a public browser.",
        client=client,
    )

    generated = generator("Open example.com")

    assert isinstance(generated.expectation, UrlMatch)
    assert generated.source == "gemini:gemini-test"
    call = client.interactions.calls[0]
    assert call["model"] == "gemini-test"
    assert call["store"] is False
    assert "response_mime_type" not in call
    assert call["response_format"]["type"] == "text"  # type: ignore[index]
    assert call["response_format"]["mime_type"] == "application/json"  # type: ignore[index]
    assert call["response_format"]["schema"]["type"] == "object"  # type: ignore[index]
    assert json.loads(call["input"]) == {  # type: ignore[arg-type]
        "user_request": "Open example.com",
        "application_context": "The agent controls a public browser.",
    }


def test_async_gemini_generator_uses_the_same_plan() -> None:
    async def run() -> None:
        client = Client(_response())
        generator = AsyncGeminiExpectationGenerator(
            model="gemini-test",
            client=client,
        )

        generated = await generator("Open example.com")

        assert isinstance(generated.expectation, UrlMatch)
        assert client.aio.interactions.calls[0]["store"] is False

    asyncio.run(run())


def test_gemini_generator_rejects_missing_structured_output() -> None:
    generator = GeminiExpectationGenerator(
        model="gemini-test",
        client=Client(Response("")),
    )

    with pytest.raises(ValueError, match="no structured expectation"):
        generator("Open example.com")


def test_gemini_generator_rejects_empty_request_before_calling_provider() -> None:
    client = Client(_response())
    generator = GeminiExpectationGenerator(model="gemini-test", client=client)

    with pytest.raises(ValueError, match="user_request cannot be empty"):
        generator(" ")

    assert client.interactions.calls == []
