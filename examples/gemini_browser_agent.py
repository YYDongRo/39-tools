from __future__ import annotations

import os
from argparse import ArgumentParser
from pathlib import Path

from agent_devtools.integrations.gemini_agent import (
    GeminiToolAgent,
    GeminiToolDefinition,
)
from agent_devtools.integrations.gemini_expectations import (
    DEFAULT_GEMINI_MODEL,
    GeminiExpectationGenerator,
)
from agent_devtools.playwright import observe_playwright_agent


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_ROOT = PROJECT_ROOT / "trace" / "gemini-browser-agent"
START_URL = (Path(__file__).parent / "gemini_browser_agent.html").resolve().as_uri()

OBSERVE_SCRIPT = """
() => {
  const visible = (element) => {
    const style = getComputedStyle(element);
    const bounds = element.getBoundingClientRect();
    return style.visibility !== "hidden" && style.display !== "none" &&
      bounds.width > 0 && bounds.height > 0;
  };
  const elements = Array.from(
    document.querySelectorAll("a, button, input, select, textarea")
  ).filter((element) => visible(element)).slice(0, 30).map((element) => ({
    selector: element.id ? `#${CSS.escape(element.id)}` : null,
    tag: element.tagName.toLowerCase(),
    text: (element.innerText || "").trim().slice(0, 200),
    type: element.getAttribute("type"),
    placeholder: element.getAttribute("placeholder"),
    value: "value" in element ? element.value.slice(0, 200) : null,
  })).filter((element) => element.selector !== null);
  return {
    url: window.location.href,
    title: document.title,
    visible_text: (document.body.innerText || "").trim().slice(0, 2000),
    interactive_elements: elements,
  };
}
"""


class BrowserTools:
    def __init__(self, page: object, allowed_start_url: str) -> None:
        self.page = page
        self.allowed_start_url = allowed_start_url

    def observe(self) -> dict[str, object]:
        state = self.page.evaluate(OBSERVE_SCRIPT)  # type: ignore[attr-defined]
        if not isinstance(state, dict):
            raise TypeError("browser observation must be an object")
        return state

    def navigate(self, url: str) -> dict[str, object]:
        if url != self.allowed_start_url:
            raise ValueError("this demo only allows navigation to its local start page")
        self.page.goto(url, timeout=10_000)  # type: ignore[attr-defined]
        return self.observe()

    def fill(self, selector: str, text: str) -> dict[str, object]:
        self.page.locator(selector).fill(text, timeout=5_000)  # type: ignore[attr-defined]
        return self.observe()

    def click(self, selector: str) -> dict[str, object]:
        self.page.locator(selector).click(timeout=5_000)  # type: ignore[attr-defined]
        return self.observe()


def tool_definitions() -> tuple[GeminiToolDefinition, ...]:
    empty_parameters: dict[str, object] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    return (
        GeminiToolDefinition(
            "observe",
            "Read the current URL, visible text, and usable CSS selectors. "
            "Call this before choosing an action and after uncertainty.",
            empty_parameters,
        ),
        GeminiToolDefinition(
            "navigate",
            f"Open the demo start page. The only allowed URL is {START_URL!r}.",
            {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
                "additionalProperties": False,
            },
        ),
        GeminiToolDefinition(
            "fill",
            "Replace the value of a visible input using a selector returned by observe.",
            {
                "type": "object",
                "properties": {
                    "selector": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["selector", "text"],
                "additionalProperties": False,
            },
        ),
        GeminiToolDefinition(
            "click",
            "Click a visible element using a selector returned by observe.",
            {
                "type": "object",
                "properties": {"selector": {"type": "string"}},
                "required": ["selector"],
                "additionalProperties": False,
            },
        ),
    )


def parse_args() -> tuple[str, bool, str]:
    parser = ArgumentParser(
        description="Run and trace a Gemini-controlled local browser task"
    )
    parser.add_argument(
        "--model",
        default=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        help="Gemini model (or set GEMINI_MODEL)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="show the browser while the agent runs",
    )
    parser.add_argument(
        "--task",
        default=(
            "Open the local shop, search for Wireless Headphones, "
            "and open that product."
        ),
        help="natural-language task sent to the browser agent",
    )
    args = parser.parse_args()
    return args.model, args.headed, args.task


def main() -> None:
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("Set GEMINI_API_KEY in this shell before running the demo.")

    from google import genai
    from playwright.sync_api import sync_playwright

    model, headed, user_request = parse_args()
    client = genai.Client()
    context_description = (
        "This is a local demo shop. Its allowed start URL is "
        f"{START_URL}. A product detail page identifies its product in "
        "h1#product-title."
    )
    expectation_generator = GeminiExpectationGenerator(
        model=model,
        application_context=context_description,
        client=client,
    )
    agent = GeminiToolAgent(
        tool_definitions(),
        model=model,
        system_instruction=(
            "You are controlling a browser to complete the user's request. "
            f"The browser starts blank and the allowed start URL is {START_URL!r}. "
            "Observe before acting. Use only selectors returned by observe. "
            "Do not claim completion until observation shows the requested final state."
        ),
        client=client,
    )

    observed_agent = None
    result: str | None = None
    run_error: Exception | None = None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        observed_agent = observe_playwright_agent(
            agent,
            BrowserTools(page, START_URL),
            page,
            TRACE_ROOT,
            expectation_generator=expectation_generator,
            methods=("navigate", "fill", "click"),
        )
        print("Running automatic verification and Gemini browser actions...", flush=True)
        try:
            result = observed_agent.run(user_request)
        except Exception as error:
            run_error = error
        finally:
            browser.close()

    report_path = observed_agent.last_report_path
    if report_path is None:
        raise RuntimeError("the demo did not create a trace report")
    print(f"Agent result: {result if result is not None else 'failed'}")
    print(f"Recorded actions: {observed_agent.last_trace.session.action_count}")
    print(f"Final outcome: {observed_agent.last_trace.session.outcome.value}")
    verification_note = observed_agent.last_trace.session.verification_note
    if verification_note is not None:
        print(f"Verification note: {verification_note}")
    print(f"Report: {report_path.resolve()}")
    if run_error is not None:
        raise run_error


if __name__ == "__main__":
    main()
