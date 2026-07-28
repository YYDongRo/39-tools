import asyncio

import pytest

from agent_devtools.integrations.playwright_final_state import (
    MAX_HEADINGS,
    MAX_VISIBLE_TEXT_CHARS,
    FinalPageState,
    observe_final_async_playwright_state,
    observe_final_playwright_state,
)


FINAL_STATE = {
    "url": "https://example.com/product",
    "title": "Example product",
    "headings": ["Wireless Headphones", "Details"],
    "visible_text": "Wireless Headphones\nIn stock",
    "text_truncated": False,
}


class Page:
    def __init__(self, state: object = FINAL_STATE) -> None:
        self.state = state
        self.arguments: dict[str, int] | None = None

    def evaluate(self, script: str, arguments: dict[str, int]) -> object:
        assert "document.body.innerText" in script
        self.arguments = arguments
        return self.state


class AsyncPage(Page):
    async def evaluate(
        self,
        script: str,
        arguments: dict[str, int],
    ) -> object:
        assert "document.body.innerText" in script
        self.arguments = arguments
        return self.state


def test_observe_final_page_state_is_bounded_and_typed() -> None:
    page = Page()

    state = observe_final_playwright_state(page)  # type: ignore[arg-type]

    assert state == FinalPageState(
        url="https://example.com/product",
        title="Example product",
        headings=("Wireless Headphones", "Details"),
        visible_text="Wireless Headphones\nIn stock",
        text_truncated=False,
    )
    assert page.arguments == {
        "maxTextChars": MAX_VISIBLE_TEXT_CHARS,
        "maxHeadings": MAX_HEADINGS,
    }


def test_observe_final_async_page_state_uses_the_same_shape() -> None:
    async def run() -> None:
        state = await observe_final_async_playwright_state(  # type: ignore[arg-type]
            AsyncPage()
        )
        assert state.headings == ("Wireless Headphones", "Details")

    asyncio.run(run())


def test_observe_final_page_state_rejects_invalid_browser_data() -> None:
    with pytest.raises(TypeError, match="final page URL"):
        observe_final_playwright_state(  # type: ignore[arg-type]
            Page({**FINAL_STATE, "url": None})
        )
