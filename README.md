# Agent DevTools

Agent DevTools is an open-source Python project for making computer-use agents
observable, debuggable, and reliable.

The current browser MVP records ordered computer-action trajectories with
arguments, timing, outcomes, failure evidence, structured page state, and
before-and-after screenshots. It writes versioned JSON traces and a static HTML
report after the agent run.

## Current features

- Typed action records built with standard-library dataclasses and enums
- Success and failure recording with duration measurement
- JSON trace output with UTC timestamps and portable paths
- Loading saved JSON traces back into typed action records
- Ordered multi-action sessions with JSON round-trip support
- Session goals with persisted task-level verification and final outcomes
- Framework-independent session recording with optional screenshot callbacks
- Safe session resumption and atomic JSON persistence
- Static HTML reports with execution, verification, and final outcome details
- Persisted action observations that remain separate from verification results
- Persisted text-state verification with evidence and mismatch reasons
- Structured failure categories based on explicit exception and verification signals
- Playwright click diagnostics with minimal structured element-state evidence
- Structured Playwright text and visibility expectations with automatic waiting
  and evidence
- Action-scoped Playwright page, console, request-failure, and HTTP-error
  evidence with likely causes
- A single Playwright executor for recorded navigate, fill, and click actions
- Stable public imports for core records and the recommended Playwright API
- Single-call Playwright click traces with screenshots, JSON, and HTML output
- A bounded Playwright agent loop that records dynamically selected actions
- A generic synchronous tool wrapper that records public method calls
- A generic sequential async tool wrapper with sync or async evidence callbacks
- Optional automatic before-and-after structured state capture with changed paths
- Automatic potential-issue warnings for repeated actions with no observed progress
- Observed-agent wrappers that capture the user request and inject recorded tools
- Optional OpenAI or Gemini generation of bounded final-state checks from that request
- A Gemini function-calling demo where model-selected browser actions are recorded
- Controlled replay for saved click actions with strict argument validation
- A dependency-free simulated action example
- An optional Playwright browser-click demo with real screenshots
- Tests for the model, recorder, serialization, and end-to-end trace flow

## Requirements

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)

## Setup

Install the core project and development dependencies:

```bash
uv sync
```

Run the test suite:

```bash
uv run pytest
```

## Quickstart

Install the optional browser dependency and Chromium, then run the reusable
quickstart:

```bash
uv sync --extra browser
uv run --extra browser playwright install chromium
uv run --extra browser python examples/quickstart.py
```

The example uses the recommended public imports:

```python
from agent_devtools import ActionOutcome
from agent_devtools.playwright import (
    RecordedPlaywrightExecutor,
    TextExpectation,
)
```

It opens a local page, records and verifies one click, captures before-and-after
screenshots, and prints the generated `report.html` path. Each run creates a new
directory under `trace/quickstart/`, so it can be run repeatedly without
overwriting earlier evidence.

### Wrap an existing agent tool object

Wrap the tools once, then give the wrapped object to the agent:

```python
from pathlib import Path

from agent_devtools import record_tools

trace = record_tools(
    original_tools,
    Path("trace/my-agent-run"),
    capture_screenshot=capture_screenshot,
    observe_state=observe_state,
)
with trace as tools:
    agent.run(task, tools=tools)

print(trace.report_path)
```

Every public synchronous method called through `tools` is recorded using its
method name and bound arguments. Return values are passed back unchanged, and a
tool exception is recorded before being raised back to the agent. Pass
`methods={"click", "fill", "scroll"}` when the object also has public methods
that should not be treated as actions. Arguments may contain sensitive data.
Calls made directly on `original_tools` cannot be intercepted.

`observe_state` is optional. When provided, it runs before and after every
recorded method call. It must return a small dictionary of current runtime
state. The action stores JSON-safe `state_before`, `state_after`, and sorted
`state_changes` paths such as `url` or `scroll.y`. Observer exceptions and
invalid return values are recorded by error type and do not change the tool
call's execution status. State collection does not verify correctness: a URL
change is evidence, not proof that the agent reached the intended URL.

For an async tool object, use `record_async_tools` and await the agent's tool
calls normally:

```python
from pathlib import Path

from agent_devtools import record_async_tools

trace = record_async_tools(
    original_tools,
    Path("trace/my-async-agent-run"),
    capture_screenshot=capture_screenshot,
    observe_state=observe_state,
)
async with trace as tools:
    await agent.run(task, tools=tools)

print(trace.report_path)
```

Public `async def` methods are automatically recorded. Screenshot, state, and
task-verification callbacks may be synchronous or asynchronous. Synchronous
methods are forwarded unchanged unless their names are explicitly selected
with `methods={...}`; an explicitly selected synchronous method is called as
`await tools.method(...)`. The first version requires tool actions to run one
at a time. It rejects overlapping calls, including calls started together with
`asyncio.gather`, because a single ordered trace cannot reliably represent
their before-and-after evidence. Run `uv run python examples/async_tools.py`
for a dependency-free example that prints the generated report path.

For Playwright tools, use the convenience wrapper so screenshots and safe page
metadata are configured automatically:

```python
from agent_devtools.playwright import record_playwright_tools

trace = record_playwright_tools(
    original_tools,
    page,
    Path("trace/my-browser-agent-run"),
)
with trace as tools:
    agent.run(task, tools=tools)
```

The default Playwright observer records URL, title, document readiness and
visibility, viewport, scroll range, element count, and a minimal focused-element
descriptor. It does not collect input values, page text, full DOM content,
cookies, browser storage, request or response bodies, or headers. URLs, titles,
tool arguments, screenshots, and error messages can still contain sensitive
information and should be handled as debugging evidence. Screenshots capture
the current viewport by default, which matches what the agent sees and keeps
reports compact. Set
`full_page_screenshots=True` only when the complete page is required.

The wrapper also listens for uncaught JavaScript `pageerror` events and
`console.error` messages, failed network requests, and HTTP 4xx/5xx responses
during each action. It waits 100 ms after the tool call by default so immediate
asynchronous errors can arrive, deduplicates identical events, and stores at
most 20 unique events per action. Network evidence contains only the method,
resource type, status or browser failure, and a URL with credentials, query
strings, and fragments removed. Reports show one prioritized, evidence-based
likely cause at the top and keep the complete event list collapsed under the
related action. Error messages and URL paths may still contain sensitive
application data. Set
`capture_browser_events=False`, `event_settle_ms=...`, or
`max_browser_events=...` to change this behavior. Successful request timelines,
headers, cookies, and request or response bodies are not collected.

Async Playwright users get the same screenshots, structured state, and browser
error evidence through the matching convenience wrapper:

```python
from agent_devtools.playwright import record_async_playwright_tools

trace = record_async_playwright_tools(
    original_tools,
    page,
    Path("trace/my-async-browser-run"),
)
async with trace as tools:
    await agent.run(task, tools=tools)
```

### Observe a complete agent run

For an agent with a `run(user_request, *, tools=...)` entry point, wrap the
agent once. The user request is passed only to `agent.run(...)`; the observer
automatically stores that same request as the session goal, injects recorded
tools, creates a unique trace directory, and writes the report afterward:

```python
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

The wrapped run returns the original agent result. Every invocation gets a new
subdirectory, so normal repeated use does not overwrite an earlier report. If
the agent raises an exception, completed actions and the HTML report still
remain available; task verification is skipped and the outcome is
`unverified`.

An optional `expectation_generator` receives the captured request before the
agent starts and returns the data-only task checks described below. The package
includes an optional OpenAI generator, so the caller does not repeat or hard-code
the user's request:

```python
from agent_devtools.playwright import openai_expectations

agent = observe_playwright_agent(
    original_agent,
    browser_tools,
    page,
    Path("trace/my-agent"),
    expectation_generator=openai_expectations(),
)

agent.run(user_request)
print(agent.last_report_path)
```

Install the optional dependency and provide your own API key through the
standard environment variable before starting the program:

```bash
uv sync --extra browser --extra llm-openai
export OPENAI_API_KEY="your-key"
```

The generator defaults to `gpt-5.6-terra`; pass `model="..."` to choose another
model. It sends only the user request and optional `application_context` to the
provider, requests strict structured output with API storage disabled, and
accepts at most five data-only checks. It never executes model-generated code.
The API key, raw provider response, and exception message are not written to the
trace.

No expectation is entered for each run. `application_context` is optional and
only helps with private applications whose routes or stable selectors cannot be
inferred from the request. Use `agent.assert_last_task_passed()` separately when
a failed or unverified result should fail a CI test.

Generation is deliberately fail-open for observability: if the dependency or
key is missing, the provider call fails, or the model cannot derive a reliable
check, the agent still runs and its actions are still recorded. The report shows
the original user request, inferred goal when available, verification source,
and a short reason for an `unverified` outcome. A provider-generated expectation
is a useful test hypothesis, not ground truth; review important checks in the
report. Without any generator, recording behaves as before and remains
`unverified`.

Async agents use `async_openai_expectations()` with
`observe_async_playwright_agent`. Run the deterministic, API-free demonstration
with:

```bash
uv run --extra browser python examples/observed_agent.py
```

#### Run a real Gemini-controlled local browser task

Gemini can supply both the task decisions and the generated final-state checks.
Install the optional dependencies, keep the key in your shell, and run:

```bash
uv sync --extra browser --extra llm-gemini
uv run --extra browser --extra llm-gemini playwright install chromium
read -s -p "Gemini API key: " GEMINI_API_KEY
echo
export GEMINI_API_KEY
uv run --extra browser --extra llm-gemini python examples/gemini_browser_agent.py --headed
```

The local browser starts blank. Gemini observes the local demo shop and chooses
`navigate`, `fill`, and `click` calls until it believes the user's request is
finished. Agent DevTools records those state-changing calls, screenshots, page
state, browser errors, and final verification in a new directory under
`trace/gemini-browser-agent/`. The command prints the exact `report.html` path.
The `observe` tool is deliberately excluded from the action timeline because it
reads state without changing the computer.
Pass `--task "..."` to send another natural-language request to the same local
shop; that exact request becomes the report goal and the verification-generator
input.

The default is the cost-oriented `gemini-3.5-flash-lite`. Override it with
`--model ...` or `GEMINI_MODEL`. The adapter uses API storage disabled and does
not write the API key or raw Gemini responses to traces. For agent decisions,
this demo does send bounded visible page text, interactive element selectors and
values, and bounded tool error messages to Gemini. Use only non-sensitive pages
until an application-specific redaction policy is added.

To add Gemini-generated verification to another observed agent without using
the demo agent, pass `gemini_expectations()` as its expectation generator. The
async equivalent is `async_gemini_expectations()`.

### Verify the final browser task

For common browser tests, declare the final success conditions instead of
writing a verification callback. Conditions run automatically when the
recorder context exits normally:

```python
from agent_devtools.playwright import (
    all_of,
    element_visible,
    property_equals,
    record_playwright_tools,
    text_contains,
    url_matches,
)

trace = record_playwright_tools(
    original_tools,
    page,
    Path("trace/youtube-test"),
    goal="Search YouTube and play a video",
    task_expectation=all_of(
        url_matches(host="youtube.com", path_prefix="/watch"),
        element_visible("video"),
        text_contains("h1", "Agent"),
        property_equals("video", "paused", False),
    ),
)

with trace as tools:
    agent.run(task, tools=tools)

trace.assert_task_passed()
```

URL checks compare components rather than the complete URL. Query strings and
fragments are ignored, and subdomains are accepted by default. Text checks can
use `text_equals(...)` or `text_contains(...)`. Every selector-based check
waits up to two seconds by default and requires exactly one matching element.
`assert_task_passed()` raises `AssertionError` for a failed or unverified task
and includes the absolute HTML report path in the message, which makes it
suitable for pytest. Async Playwright uses the same task checks and assertion
method with `record_async_playwright_tools`.

These checks are deterministic and local. They do not infer the goal or call an
LLM. Their data-only structure is intended to be a safe target for a future
optional expectation generator.

## Record a simulated action

Run the dependency-free example:

```bash
uv run python examples/record_action.py
```

It writes a trace to:

```text
trace/action.json
```

## Record a real browser click

Install the optional browser dependency and Chromium once:

```bash
uv sync --extra browser
uv run --extra browser playwright install chromium
```

On Ubuntu or WSL, install Chromium and its required system packages together:

```bash
uv run --extra browser playwright install --with-deps chromium
```

Run the local browser demo:

```bash
uv run --extra browser python examples/browser_click.py
```

The demo opens a local HTML page in headless Chromium, records a real click,
verifies the resulting status text, and creates:

```text
trace/browser-click/<run-id>/
├── action.json
├── before.png
├── after.png
└── report.html
```

Open `report.html` to inspect the verified final outcome, expected and observed
status text, action details, and before-and-after screenshots on one page.
Generated traces are ignored by Git.

## Try it from another project

Before publishing a package release, install this repository as an editable
dependency from a separate project. Replace `/path/to/agent-devtools` with the
repository path visible inside WSL:

```bash
mkdir agent-devtools-consumer-test
cd agent-devtools-consumer-test
uv init --python 3.14
uv add --editable --extra browser /path/to/agent-devtools
uv run playwright install --with-deps chromium
```

Create `main.py`:

```python
from pathlib import Path

from playwright.sync_api import sync_playwright

from agent_devtools.integrations.playwright import (
    TextExpectation,
    expect_text,
    record_playwright_click_trace,
)


trace_dir = Path("trace/success")

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_content(
        """
        <button id="save"
                onclick="document.querySelector('#status').textContent = 'Saved'">
          Save
        </button>
        <p id="status">Not saved</p>
        """
    )

    action = record_playwright_click_trace(
        page,
        "#save",
        trace_dir,
        verification=expect_text(
            page,
            TextExpectation(selector="#status", expected="Saved"),
        ),
    )
    browser.close()

print(f"Final outcome: {action.outcome.value}")
print(f"Report: {(trace_dir / 'report.html').resolve()}")
```

Run it:

```bash
uv run python main.py
```

The single `record_playwright_click_trace()` call captures both screenshots,
records and verifies the click, and writes `action.json` and `report.html`.
It refuses to overwrite a non-empty trace directory; use a new directory for
each run. To exercise a verification failure, change `expected="Saved"` to
`expected="Published"` and change the directory to `Path("trace/failure")`.

From WSL, open the generated files in Windows Explorer:

```bash
explorer.exe "$(wslpath -w "$PWD/trace")"
```

Add `trace/` to the consumer project's `.gitignore` when generated reports
should remain local.

### Inspect a controlled browser failure

Run a second local demo that deliberately clicks a missing element:

```bash
uv run --extra browser python examples/browser_failure.py
```

It records the Playwright timeout instead of re-raising it and creates:

```text
trace/browser-failure/
├── action.json
├── before.png
├── after.png
└── report.html
```

Open this `report.html` to inspect the failed selector, timeout, duration,
`target_not_found` diagnosis, structured evidence, and unchanged browser state.

### Record a continuous browser session

Run three actions in one browser and preserve the page state between them:

```bash
uv run --extra browser python examples/browser_session.py
```

The session opens a form, enters a task name, and then deliberately uses the
wrong selector for the confirmation button. It creates:

```text
trace/browser-session/<run-id>/
├── session.json
├── report.html
└── actions/
    ├── 001/
    │   ├── before.png
    │   └── after.png
    ├── 002/
    │   ├── before.png
    │   └── after.png
    └── 003/
        ├── before.png
        └── after.png
```

Each action runs in the same page and browser context, so every screenshot
reflects the state produced by the preceding actions.

`SessionRecorder` handles screenshot paths, action numbering, session updates,
JSON persistence, and HTML report generation after every action. The screenshot
callback is integration-specific, so the core package does not depend on a
browser or desktop automation framework.

## JSON trace format

```json
{
  "schema_version": 5,
  "action_type": "click",
  "arguments": {
    "selector": "#agent-action"
  },
  "start_time": "2026-07-18T07:06:12.398917+00:00",
  "duration_ms": 32,
  "status": "success",
  "screenshot_before": "before.png",
  "screenshot_after": "after.png",
  "failure_reason": null,
  "failure_category": null,
  "failure_evidence": {},
  "observations": {},
  "verification": null
}
```

Action arguments must contain JSON-serializable values. Timestamps must be
timezone-aware and are written in UTC.

## Library usage

```python
from pathlib import Path

from agent_devtools.recorder import record_action
from agent_devtools.serialization import write_action_json
from agent_devtools.verification import verify_text_state


action = record_action(
    action_type="click",
    arguments={"x": 100, "y": 200},
    operation=lambda: None,
    verification=lambda: verify_text_state(
        expected_state="Action complete",
        observed_state="Action complete",
    ),
)
write_action_json(action, Path("trace/action.json"))
```

`record_action()` converts operation exceptions into failed action records and
skips verification when execution fails. After successful execution, it runs an
optional verification callback and attaches the returned `VerificationResult`.
Verification callback errors are re-raised, and the operation's return value is
currently ignored.

## Verify observed text state

Compare expected and observed UI text without depending on a browser framework:

```python
from agent_devtools.verification import verify_text_state


verification = verify_text_state(
    expected_state="Action complete",
    observed_state="Waiting for the agent.",
    evidence={"selector": "#status"},
)
print(verification.passed)
print(verification.failure_reason)
print(verification.failure_category)
```

Pass a verification callback to `record_action()` or `SessionRecorder.record()`
to run verification before JSON and HTML are written. Execution status and
verification status remain separate.
`ActionRecord.outcome` derives the final result: execution or verification
failure means `failure`, a passed verification means `success`, and a successful
action without verification means `unverified`.

For Playwright, declare an exact text expectation instead of manually reading
the page and constructing a result:

```python
from agent_devtools.integrations.playwright import (
    TextExpectation,
    expect_text,
    record_playwright_click,
)


expectation = TextExpectation(
    selector="#status",
    expected="Saved",
    timeout_ms=2_000,
)
action = record_playwright_click(
    page,
    "#save",
    verification=expect_text(page, expectation),
)
```

`expect_text()` waits for exactly one matching element and the expected text.
It records the selector, match count, timeout, expected text, and observed text
as verification evidence. A missing element or different text is a verification
failure; Playwright or page errors are still raised as verifier errors.

Dynamic actions can declare that an element must become visible after the
action:

```python
from agent_devtools.integrations.playwright import (
    InputValueExpectation,
    PlaywrightAction,
    TextExpectation,
    VisibilityExpectation,
)


action = PlaywrightAction(
    "navigate",
    {"url": target_url},
    expectation=VisibilityExpectation("#search"),
)

search_action = PlaywrightAction(
    "click",
    {"selector": "#search-button"},
    expectation=TextExpectation(
        "#video-result",
        "Result for: Agent debugging",
    ),
)

fill_action = PlaywrightAction(
    "fill",
    {"selector": "#search", "text": "Agent debugging"},
    expectation=InputValueExpectation(),
)
```

`run_playwright_agent()` automatically selects the text, visibility, or input
value verifier after each action executes. `InputValueExpectation()` derives
the expected selector and value from the fill arguments, so they are not
repeated. Every Playwright fill records `input_value_after` as an observation,
even without an expectation; that action remains unverified. Every supported
Playwright action also records `page_url_before` and `page_url_after` without
treating a redirect as a mismatch. The HTML report displays one URL when it is
unchanged and shows the before-and-after URLs only when navigation occurs.

### Record a task with one executor

Create one executor for a browser task, then send all supported actions through
it:

```python
from pathlib import Path

from agent_devtools.integrations.playwright import (
    InputValueExpectation,
    RecordedPlaywrightExecutor,
    TextExpectation,
    VisibilityExpectation,
)


with RecordedPlaywrightExecutor(
    page,
    Path("trace/my-agent-run"),
) as executor:
    executor.navigate(
        target_url,
        expectation=VisibilityExpectation("#search"),
    )
    executor.fill(
        "#search",
        "Agent debugging",
        expectation=InputValueExpectation(),
    )
    executor.click(
        "#search-button",
        expectation=TextExpectation(
            "#video-result",
            "Result for: Agent debugging",
        ),
    )

print(executor.report_path)
```

The executor owns the session recorder and screenshot callback. Each method
updates the same `session.json` and `report.html`. A dynamic agent can instead
call `executor.run(decide_next_action)`. Actions made directly through the raw
Playwright `page` are not intercepted and therefore are not recorded.

Generated traces can contain sensitive page URLs, typed text, screenshots, and
exception messages. Keep trace directories private unless they have been
reviewed and redacted.

Run a controlled executor failure that clicks a missing element:

```bash
uv run --extra browser python examples/executor_click_failure.py
```

The command prints the generated `report.html` path. Each run writes to a new
directory under `trace/executor-click-failure/` and records the click as
`target_not_found` with its selector evidence and before-and-after screenshots.

Run the corresponding fill failure demo against a readonly input:

```bash
uv run --extra browser python examples/executor_fill_failure.py
```

It writes a new trace under `trace/executor-fill-failure/` and records
`target_not_editable` with visibility, enabled, and editability evidence.

## Failure categories

Core recording uses four conservative categories:

- `timeout` for exceptions whose type is `TimeoutError`;
- `operation_error` for other operation exceptions;
- `verification_mismatch` when expected and observed text differ;
- `unknown` when existing evidence does not support a more specific category.

The original failure reason is always preserved. The classifier does not infer
`wrong_target`, `blocked_target`, or `page_not_ready` from error-message text.

The optional Playwright adapter can refine failed click and fill actions using
direct element observations:

- `target_not_found` when the selector matches no elements;
- `target_ambiguous` when the selector matches multiple elements;
- `target_not_visible` when exactly one target exists but is not visible;
- `target_disabled` when exactly one target is visible but disabled;
- `target_not_editable` when a fill target exists but cannot accept input.

```python
from agent_devtools.integrations.playwright import record_playwright_click


action = record_playwright_click(
    page,
    "#confirm",
    timeout_ms=500,
)
print(action.failure_category)
print(action.failure_evidence)
```

Evidence contains only the selector, match count, visibility, enabled state,
fill editability, and diagnostic error type when inspection itself fails. It
does not capture the full DOM or page text.

## Load an existing trace

Load a saved JSON trace and regenerate its HTML report without running the
original action again:

```python
from pathlib import Path

from agent_devtools.report import write_action_html
from agent_devtools.serialization import read_action_json


trace_dir = Path("trace/browser-failure")
action = read_action_json(trace_dir / "action.json")
write_action_html(action, trace_dir / "report.html")
```

The loader accepts action schema versions 1 through 5. Version 1 failures load
with the `unknown` category; versions 1 and 2 load with empty failure evidence;
versions 1 through 3 load without a verification result; versions 1 through 4
load with empty observations. It validates required fields, field types, status,
observations, verification data, and timestamp format before returning an
`ActionRecord`.

## Replay a saved click

Replay uses a caller-provided click executor, so a saved trace cannot choose a
URL or execute arbitrary code:

```python
from pathlib import Path

from agent_devtools.replay import replay_click
from agent_devtools.serialization import read_action_json


source_action = read_action_json(Path("trace/browser-click/action.json"))


def execute_click(selector: str, timeout_ms: int | None) -> None:
    if timeout_ms is None:
        page.locator(selector).click()
    else:
        page.locator(selector).click(timeout=timeout_ms)

result = replay_click(
    source_action,
    execute_click=execute_click,
)
print(result.replayed_action.status)
print(result.outcome_matches)
```

Only `click` actions with a non-empty `selector` and optional positive
`timeout_ms` are accepted. The caller creates the page and chooses its URL.
Unknown source failures are never reported as stable reproductions.

Run the controlled browser failure replay example:

```bash
uv run --extra browser python examples/browser_replay.py
```

The example records a controlled timeout, saves and reloads it, and then replays
it in a fresh page using the repository's fixed local HTML. It creates:

```text
trace/browser-replay/<run-id>/
├── original.json
├── replay.json
├── before.png
├── after.png
└── report.html
```

## Record actions in a session

`SessionRecorder` records actions in execution order and updates the JSON and
HTML report after every action:

```python
from pathlib import Path

from agent_devtools.serialization import read_session_json
from agent_devtools.session_recorder import SessionRecorder
from agent_devtools.verification import verify_text_state


with SessionRecorder(
    Path("trace/my-session"),
    goal="Open the requested item",
    task_verification=lambda: verify_text_state(
        "Item open",
        "Item open",
    ),
) as recorder:
    recorder.record(
        "click",
        {"step": 1},
        lambda: None,
    )
    recorder.record("click", {"step": 2}, lambda: None)

loaded_session = read_session_json(Path("trace/my-session/session.json"))
print(loaded_session.action_count)
print(loaded_session.has_failures)
print(loaded_session.outcome)
```

Pass a screenshot callback to `SessionRecorder` to capture before-and-after
images automatically. Action count and failure state are derived from the saved
action list. The HTML timeline leads with the final task result, then summarizes
successful executions, action failures, and action-check coverage. An action
that executed successfully without its own check is shown neutrally instead of
as a warning; final task verification remains separate and prominent. Failure
categories include execution and verification failures. Each action shows its
execution status, optional action check, timing, arguments, failure details, and
screenshots.

Session reports automatically analyze repeated no-progress actions. When at
least three consecutive successful calls use the same action type and arguments,
and complete before-and-after structured state shows no change, a compact
`Potential issues` section appears above the timeline. It links directly to the
related actions and keeps evidence and inspection suggestions collapsed until
opened. Findings are warnings rather than verification results: they do not
change action or task outcomes and do not claim that the task is wrong.

The same deterministic analysis can be run on a loaded session without changing
the saved JSON schema:

```python
from agent_devtools import analyze_session, read_session_json

session = read_session_json(Path("trace/my-session/session.json"))
for finding in analyze_session(session):
    print(finding.title, finding.action_numbers)
```

When `task_verification` is configured, leaving the `with` block normally runs
it automatically and writes the final report. If an unhandled agent exception
escapes, completed actions remain persisted, task verification is skipped, and
the task stays `unverified`. Integrations that need manual lifecycle control can
omit `task_verification` and call the lower-level `verify_task()` method.

`ActionSession.outcome` is `success` or `failure` when task verification runs
and `unverified` otherwise. Intermediate action failures remain visible, but a
passed task verification can show that the agent recovered and completed the
user goal. Session schema version 2 stores the goal and task verification; the
loader remains compatible with schema version 1 sessions.

Starting a recorder in a non-empty directory raises `FileExistsError` instead
of overwriting evidence. Resume an existing session explicitly:

```python
recorder = SessionRecorder.resume(Path("trace/my-session"))
recorder.record("click", {"step": 3}, lambda: None)
```

Session JSON is written to a temporary file and atomically replaced, so an
interrupted update does not leave a partially written trace.

### Trace an agent-like browser trajectory

Run a deterministic local task that searches for a video result and plays it:

```bash
uv run --extra browser python examples/video_search_agent.py
```

The rule-based agent repeatedly observes the current page, then returns a
`PlaywrightAction` or stops when the player is running. It can skip steps that
the page has already completed; it does not execute a fixed action list.
`RecordedPlaywrightExecutor` owns the recorder and sends every dynamic decision
through the existing action recording path. It captures before-and-after
screenshots and updates `session.json` and `report.html` after every action. The
browser starts at `about:blank`, so navigation to the local site is the first
recorded action. That navigation is verified by waiting for the search field to
become visible, and the final URL is retained as evidence. The fill action
records its actual input value as an observation. When the agent finishes, the
final report is already complete.

The task creates:

```text
trace/video-search-agent/<run-id>/
├── session.json
├── report.html
└── actions/
    ├── 001/
    │   ├── before.png
    │   └── after.png
    ├── 002/
    ├── 003/
    ├── 004/
    └── 005/
```

After all actions finish, the recorder context automatically checks that the
local player status is `Playing: Agent debugging`. The report shows the task
goal, task verification, and final task outcome separately from the five action
results. This example demonstrates the interception point an agent integration
can use; it does not automatically connect to arbitrary third-party agents or
the real YouTube website. A future integration can replace the rule-based
decision function with an LLM or framework callback without changing the
recording path.

### Try the live YouTube demo

Run the same agent-like loop against the real YouTube website:

```bash
uv run --extra browser python examples/youtube_agent_demo.py --headed
```

The live demo wraps a small external-style tool object once, then lets the agent
call its normal `navigate`, `fill`, and `click` methods. It searches for
`computer use agents`, opens the first regular video result, and writes its
report under `trace/youtube-agent/<run-id>/`. The Playwright convenience wrapper
automatically captures screenshots and structured page state around each tool
call. Pass a different search with `--query "your search"`. This is a manual
demonstration, not a CI test: cookie dialogs, localization, advertisements,
network failures, and YouTube UI changes can alter or block the trajectory. The
screenshots and typed query are stored locally in the trace and may contain
sensitive content.

## Current limitations

- Async tool recording supports sequential actions only; concurrent actions are
  rejected, and JSON/HTML persistence still uses synchronous local file writes
- Replay is limited to single synchronous click actions; there is no session replay
- No general desktop screenshot capture
- No built-in desktop or Android structured state observer
- No CLI, dashboard, or recovery system
- The observed-agent MVP requires `run(user_request, *, tools=...)`; other
  framework call shapes need adapters
- Playwright navigate, click, and fill recording are the only current runtime
  integration; structured failure diagnostics are limited to click and fill
- Browser runtime evidence records failed requests and HTTP 4xx/5xx responses,
  but not successful request timelines, redirects, headers, cookies, or bodies
- Deterministic expected states can be supplied directly; the optional OpenAI
  generator can propose bounded checks from the user request, but generated
  checks are not ground truth
- Structured state changes are evidence only; they are not automatic verification
- Automatic trajectory analysis currently covers browser/runtime errors and
  three or more identical consecutive actions with unchanged structured state;
  it is not general semantic root-cause analysis
- Action-level Playwright expectations support exact text and input values,
  plus single-element visibility; task checks additionally support component
  URL matching, contained text, and scalar DOM property equality

## License

Agent DevTools is available under the [MIT License](LICENSE).
