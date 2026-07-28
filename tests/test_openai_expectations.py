import asyncio
import json

import pytest

from agent_devtools.integrations.openai_expectations import (
    AsyncOpenAIExpectationGenerator,
    OpenAIExpectationGenerator,
)
from agent_devtools.integrations.playwright_task import UrlMatch


class Response:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class Responses:
    def __init__(self, response: Response) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> Response:
        self.calls.append(kwargs)
        return self.response


class Client:
    def __init__(self, response: Response) -> None:
        self.responses = Responses(response)


class AsyncResponses(Responses):
    async def create(self, **kwargs: object) -> Response:
        self.calls.append(kwargs)
        return self.response


class AsyncClient:
    def __init__(self, response: Response) -> None:
        self.responses = AsyncResponses(response)


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


def test_openai_generator_uses_structured_output_without_storing_response() -> None:
    client = Client(_response())
    generator = OpenAIExpectationGenerator(
        model="gpt-test",
        application_context="The agent controls a public browser.",
        client=client,
    )

    generated = generator("Open example.com")

    assert isinstance(generated.expectation, UrlMatch)
    assert generated.source == "openai:gpt-test"
    call = client.responses.calls[0]
    assert call["model"] == "gpt-test"
    assert call["store"] is False
    assert call["text"]["format"]["strict"] is True  # type: ignore[index]
    user_payload = json.loads(call["input"][1]["content"])  # type: ignore[index]
    assert user_payload == {
        "user_request": "Open example.com",
        "application_context": "The agent controls a public browser.",
    }


def test_async_openai_generator_uses_the_same_plan() -> None:
    async def run() -> None:
        client = AsyncClient(_response())
        generator = AsyncOpenAIExpectationGenerator(
            model="gpt-test",
            client=client,
        )

        generated = await generator("Open example.com")

        assert isinstance(generated.expectation, UrlMatch)
        assert client.responses.calls[0]["store"] is False

    asyncio.run(run())


def test_openai_generator_rejects_missing_structured_output() -> None:
    generator = OpenAIExpectationGenerator(
        model="gpt-test",
        client=Client(Response("")),
    )

    with pytest.raises(ValueError, match="no structured expectation"):
        generator("Open example.com")
