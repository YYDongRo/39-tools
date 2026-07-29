# Playwright and tool integrations

Use these lower-level integrations when the agent does not use Browser Use, or
when direct control over tools and verification is required.

## Wrap an existing Playwright tool object

Wrap the tools once, then give the wrapped object to the agent:

```python
from pathlib import Path

from agent_devtools.playwright import record_playwright_tools

trace = record_playwright_tools(
    original_tools,
    page,
    Path("trace/my-agent-run"),
)

with trace as tools:
    agent.run(task, tools=tools)

print(trace.report_path)
```

Public tool calls made through `tools` are recorded. Calls made directly on
`original_tools` or the raw Playwright `page` cannot be intercepted.

The wrapper configures viewport screenshots, compact page state, uncaught page
errors, `console.error` messages, failed requests, and HTTP 4xx/5xx evidence.
It does not collect cookies, browser storage, headers, request bodies, response
bodies, password values, or the complete DOM.

For async tool objects, use `record_async_playwright_tools(...)` and
`async with`. The current recorder requires actions to run sequentially and
rejects overlapping calls.

## Observe an agent run

An agent with a `run(user_request, *, tools=...)` entry point can be wrapped at
the run boundary:

```python
from pathlib import Path

from agent_devtools.playwright import observe_playwright_agent

agent = observe_playwright_agent(
    original_agent,
    browser_tools,
    page,
    Path("trace/my-agent"),
)

result = agent.run("Open the requested page and click the visible target")
print(agent.last_report_path)
```

The wrapper stores the exact user request, injects the recorded tools, and
writes a report after each run. If the agent raises, completed actions remain
available and the final task result stays `unverified`.

## Deterministic final checks

Common browser results can be checked locally with data-only expectations:

```python
from agent_devtools.playwright import (
    all_of,
    element_visible,
    property_equals,
    text_contains,
    url_matches,
)

task_expectation = all_of(
    url_matches(host="youtube.com", path_prefix="/watch"),
    element_visible("video"),
    text_contains("h1", "Agent"),
    property_equals("video", "paused", False),
)
```

URL checks compare components instead of requiring one exact URL. Query strings
and fragments are ignored, and subdomains are accepted by default.

Action-level Playwright expectations include exact text, contained text,
single-element visibility, and input value checks. `InputValueExpectation()`
derives its expected selector and value from the recorded fill action, so the
developer does not repeat them.

## Optional AI-assisted verification

The observed-agent integration can generate bounded checks from the user
request before a run, or assess a bounded snapshot of the final page afterward.
OpenAI and Gemini adapters are optional.

Generated checks and final-page assessments are hypotheses, not ground truth.
Provider failures do not stop recording; they leave the final outcome
`unverified` with a short safe reason. Provider keys and raw responses are not
written to traces.

## Generic tools

Framework-independent synchronous objects can use `record_tools(...)`:

```python
from agent_devtools import record_tools

trace = record_tools(
    original_tools,
    Path("trace/my-run"),
    capture_screenshot=capture_screenshot,
    observe_state=observe_state,
)

with trace as tools:
    agent.run(task, tools=tools)
```

Use `record_async_tools(...)` for async tools. State observers are optional and
must return a small dictionary. The recorder stores JSON-safe before and after
state plus changed paths; state changes are evidence and do not automatically
prove correctness.

## Examples

- `examples/quickstart.py`: one local recorded and verified click
- `examples/observed_agent.py`: deterministic observed-agent run
- `examples/async_tools.py`: dependency-free async tool wrapper
- `examples/video_search_agent.py`: dynamic local browser trajectory
- `examples/youtube_agent_demo.py`: manual live YouTube demonstration
- `examples/browser_failure.py`: controlled missing-target failure
