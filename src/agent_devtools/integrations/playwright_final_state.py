from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from agent_devtools.verification import VerificationResult


if TYPE_CHECKING:
    from playwright.async_api import Page as AsyncPage
    from playwright.sync_api import Page


MAX_VISIBLE_TEXT_CHARS = 6_000
MAX_HEADINGS = 20
MAX_HEADING_CHARS = 500

_FINAL_PAGE_STATE_SCRIPT = """
({ maxTextChars, maxHeadings }) => {
  const visibleText = document.body ? document.body.innerText.trim() : "";
  const headings = Array.from(document.querySelectorAll("h1, h2, h3"))
    .map((element) => element.innerText.trim())
    .filter(Boolean)
    .slice(0, maxHeadings);

  return {
    url: window.location.href,
    title: document.title,
    headings,
    visible_text: visibleText.slice(0, maxTextChars),
    text_truncated: visibleText.length > maxTextChars,
  };
}
"""


@dataclass(frozen=True)
class FinalPageState:
    url: str
    title: str
    headings: tuple[str, ...]
    visible_text: str
    text_truncated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "title": self.title,
            "headings": list(self.headings),
            "visible_text": self.visible_text,
            "text_truncated": self.text_truncated,
        }


@dataclass(frozen=True)
class FinalStateAssessment:
    verification: VerificationResult | None
    source: str
    note: str | None = None

    def __post_init__(self) -> None:
        if self.verification is not None and not isinstance(
            self.verification, VerificationResult
        ):
            raise TypeError("verification must be a VerificationResult or None")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source cannot be empty")
        if self.note is not None and (
            not isinstance(self.note, str) or not self.note.strip()
        ):
            raise ValueError("note cannot be empty")


FinalStateVerifier: TypeAlias = Callable[
    [str, FinalPageState],
    FinalStateAssessment | VerificationResult | None,
]
AsyncFinalStateVerifier: TypeAlias = Callable[
    [str, FinalPageState],
    FinalStateAssessment
    | VerificationResult
    | None
    | Awaitable[FinalStateAssessment | VerificationResult | None],
]


def observe_final_playwright_state(page: Page) -> FinalPageState:
    state = page.evaluate(
        _FINAL_PAGE_STATE_SCRIPT,
        {
            "maxTextChars": MAX_VISIBLE_TEXT_CHARS,
            "maxHeadings": MAX_HEADINGS,
        },
    )
    return _normalize_final_page_state(state)


async def observe_final_async_playwright_state(
    page: AsyncPage,
) -> FinalPageState:
    state = await page.evaluate(
        _FINAL_PAGE_STATE_SCRIPT,
        {
            "maxTextChars": MAX_VISIBLE_TEXT_CHARS,
            "maxHeadings": MAX_HEADINGS,
        },
    )
    return _normalize_final_page_state(state)


def _normalize_final_page_state(state: object) -> FinalPageState:
    if not isinstance(state, dict):
        raise TypeError("final Playwright page state must be an object")

    url = state.get("url")
    title = state.get("title")
    headings = state.get("headings")
    visible_text = state.get("visible_text")
    text_truncated = state.get("text_truncated")
    if not isinstance(url, str):
        raise TypeError("final page URL must be a string")
    if not isinstance(title, str):
        raise TypeError("final page title must be a string")
    if not isinstance(headings, list) or not all(
        isinstance(heading, str) for heading in headings
    ):
        raise TypeError("final page headings must be strings")
    if not isinstance(visible_text, str):
        raise TypeError("final page visible text must be a string")
    if not isinstance(text_truncated, bool):
        raise TypeError("final page text_truncated must be a boolean")

    return FinalPageState(
        url=url,
        title=title,
        headings=tuple(
            heading[:MAX_HEADING_CHARS] for heading in headings[:MAX_HEADINGS]
        ),
        visible_text=visible_text[:MAX_VISIBLE_TEXT_CHARS],
        text_truncated=(
            text_truncated or len(visible_text) > MAX_VISIBLE_TEXT_CHARS
        ),
    )


__all__ = [
    "AsyncFinalStateVerifier",
    "FinalPageState",
    "FinalStateAssessment",
    "FinalStateVerifier",
    "MAX_HEADINGS",
    "MAX_HEADING_CHARS",
    "MAX_VISIBLE_TEXT_CHARS",
    "observe_final_async_playwright_state",
    "observe_final_playwright_state",
]
