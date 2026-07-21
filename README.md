# Agent DevTools

Agent DevTools is an open-source Python project for making computer-use agents
observable, debuggable, and reliable.

The current MVP records one computer action with its arguments, timing, outcome,
failure reason, and optional before-and-after screenshot paths. Records can be
written as versioned JSON traces.

## Current features

- Typed action records built with standard-library dataclasses and enums
- Success and failure recording with duration measurement
- JSON trace output with UTC timestamps and portable paths
- Loading saved JSON traces back into typed action records
- Ordered multi-action sessions with JSON round-trip support
- Framework-independent session recording with optional screenshot callbacks
- Safe session resumption and atomic JSON persistence
- Static HTML reports with action details and session failure-category summaries
- Persisted text-state verification with evidence and mismatch reasons
- Structured failure categories based on explicit exception and verification signals
- Playwright click diagnostics with minimal structured element-state evidence
- Controlled replay for saved click actions with strict argument validation
- A dependency-free simulated action example
- An optional Playwright browser-click demo with real screenshots
- Tests for the model, recorder, serialization, and end-to-end trace flow

## Requirements

- Python 3.14 or newer
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

Run the local browser demo:

```bash
uv run --extra browser python examples/browser_click.py
```

The demo opens a local HTML page in headless Chromium, records a real click, and
creates:

```text
trace/browser-click/
├── action.json
├── before.png
├── after.png
└── report.html
```

Open `report.html` to inspect the action details and before-and-after screenshots
on one page. Generated traces are ignored by Git.

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
  "schema_version": 4,
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


action = record_action(
    action_type="click",
    arguments={"x": 100, "y": 200},
    operation=lambda: None,
)
write_action_json(action, Path("trace/action.json"))
```

`record_action()` converts operation exceptions into failed action records. It
does not re-raise them, and the operation's return value is currently ignored.

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

Set `ActionRecord.verification` before writing an action or session to preserve
the result in JSON. Execution status and verification status remain separate.

## Failure categories

Core recording uses four conservative categories:

- `timeout` for exceptions whose type is `TimeoutError`;
- `operation_error` for other operation exceptions;
- `verification_mismatch` when expected and observed text differ;
- `unknown` when existing evidence does not support a more specific category.

The original failure reason is always preserved. The classifier does not infer
`wrong_target`, `blocked_target`, or `page_not_ready` from error-message text.

The optional Playwright adapter can refine a failed click using direct element
observations:

- `target_not_found` when the selector matches no elements;
- `target_not_visible` when exactly one target exists but is not visible;
- `target_disabled` when exactly one target is visible but disabled.

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

Evidence contains only the selector, match count, visibility, enabled state, and
diagnostic error type when inspection itself fails. It does not capture the full
DOM or page text.

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

The loader accepts action schema versions 1, 2, 3, and 4. Version 1 failures
load with the `unknown` category; versions 1 and 2 load with empty failure
evidence; versions 1 through 3 load without a verification result. It validates
required fields, field types, status, verification data, and timestamp format
before returning an `ActionRecord`.

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


recorder = SessionRecorder(Path("trace/my-session"))
recorder.record("click", {"step": 1}, lambda: None)
recorder.record("click", {"step": 2}, lambda: None)

loaded_session = read_session_json(Path("trace/my-session/session.json"))
print(loaded_session.action_count)
print(loaded_session.has_failures)
```

Pass a screenshot callback to `SessionRecorder` to capture before-and-after
images automatically. Action count and failure state are derived from the saved
action list. The HTML timeline displays success and failure totals, a breakdown
of failure categories, and each action's status, timing, arguments, failure
reason, and screenshots.

Starting a recorder in a non-empty directory raises `FileExistsError` instead
of overwriting evidence. Resume an existing session explicitly:

```python
recorder = SessionRecorder.resume(Path("trace/my-session"))
recorder.record("click", {"step": 3}, lambda: None)
```

Session JSON is written to a temporary file and atomically replaced, so an
interrupted update does not leave a partially written trace.

## Current limitations

- Session recording is synchronous
- Replay is limited to single synchronous click actions; there is no session replay
- No general desktop screenshot capture
- No CLI, dashboard, or recovery system
- Playwright click recording and diagnostics are the only current runtime integration
- HTML reports and session outcomes do not yet use verification results
