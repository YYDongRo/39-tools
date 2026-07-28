import asyncio
import json

import pytest

from agent_devtools.integrations.gemini_final_state import (
    AsyncGeminiFinalStateVerifier,
    GeminiFinalStateVerifier,
)
from agent_devtools.integrations.playwright_final_state import FinalPageState


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


FINAL_STATE = FinalPageState(
    url="https://example.com/product",
    title="Wireless Headphones",
    headings=("Wireless Headphones",),
    visible_text="Wireless Headphones\nIn stock",
    text_truncated=False,
)


def _response(verdict: str) -> Response:
    return Response(
        json.dumps(
            {
                "verdict": verdict,
                "summary": "The product page is open.",
                "evidence": ["The heading is Wireless Headphones."],
            }
        )
    )


def test_gemini_final_state_verifier_uses_real_page_evidence() -> None:
    client = Client(_response("passed"))
    verifier = GeminiFinalStateVerifier(
        model="gemini-test",
        client=client,
    )

    assessment = verifier("Open Wireless Headphones", FINAL_STATE)

    assert assessment.verification is not None
    assert assessment.verification.passed is True
    assert assessment.source == "gemini:gemini-test:final-state"
    assert assessment.verification.evidence["assessment_type"] == (
        "ai_final_state"
    )
    call = client.interactions.calls[0]
    assert call["store"] is False
    response_format = call["response_format"]
    assert response_format["mime_type"] == "application/json"  # type: ignore[index]
    payload = json.loads(call["input"])  # type: ignore[arg-type]
    assert payload["user_request"] == "Open Wireless Headphones"
    assert payload["final_page_state"] == FINAL_STATE.to_dict()


def test_gemini_final_state_verifier_preserves_a_failed_verdict() -> None:
    assessment = GeminiFinalStateVerifier(
        model="gemini-test",
        client=Client(_response("failed")),
    )("Open Wireless Headphones", FINAL_STATE)

    assert assessment.verification is not None
    assert assessment.verification.passed is False
    assert assessment.verification.failure_reason == "The product page is open."


def test_gemini_final_state_verifier_can_remain_unverified() -> None:
    assessment = GeminiFinalStateVerifier(
        model="gemini-test",
        client=Client(_response("unverified")),
    )("Open Wireless Headphones", FINAL_STATE)

    assert assessment.verification is None
    assert assessment.note == "The product page is open."


def test_async_gemini_final_state_verifier_uses_the_same_result() -> None:
    async def run() -> None:
        assessment = await AsyncGeminiFinalStateVerifier(
            model="gemini-test",
            client=Client(_response("passed")),
        )("Open Wireless Headphones", FINAL_STATE)
        assert assessment.verification is not None
        assert assessment.verification.passed is True

    asyncio.run(run())


def test_gemini_final_state_verifier_rejects_invalid_json() -> None:
    verifier = GeminiFinalStateVerifier(
        model="gemini-test",
        client=Client(Response("not-json")),
    )

    with pytest.raises(ValueError, match="invalid assessment JSON"):
        verifier("Open Wireless Headphones", FINAL_STATE)
