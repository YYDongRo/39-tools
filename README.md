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
- Static HTML reports for individual actions and multi-action timelines
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

Open this `report.html` to inspect the failed selector, timeout, duration, failure
reason, and unchanged browser state.

### Record a continuous browser session

Run three actions in one browser and preserve the page state between them:

```bash
uv run --extra browser python examples/browser_session.py
```

The session opens a form, enters a task name, and then deliberately uses the
wrong selector for the confirmation button. It creates:

```text
trace/browser-session/
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

## JSON trace format

```json
{
  "schema_version": 1,
  "action_type": "click",
  "arguments": {
    "selector": "#agent-action"
  },
  "start_time": "2026-07-18T07:06:12.398917+00:00",
  "duration_ms": 32,
  "status": "success",
  "screenshot_before": "before.png",
  "screenshot_after": "after.png",
  "failure_reason": null
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

The loader validates schema version 1, required fields, field types, status, and
timestamp format before returning an `ActionRecord`.

## Group actions into a session

An `ActionSession` keeps multiple action records in execution order:

```python
from pathlib import Path

from agent_devtools.recorder import record_action
from agent_devtools.report import write_session_html
from agent_devtools.serialization import read_session_json, write_session_json
from agent_devtools.session import ActionSession


actions = [
    record_action("click", {"step": 1}, lambda: None),
    record_action("click", {"step": 2}, lambda: None),
]
session = ActionSession(actions=actions)
write_session_json(session, Path("trace/session.json"))

loaded_session = read_session_json(Path("trace/session.json"))
write_session_html(loaded_session, Path("trace/session.html"))
print(loaded_session.action_count)
print(loaded_session.has_failures)
```

The session JSON stores the ordered action records. Action count and failure
state are derived from that list instead of being duplicated in the file. The
HTML timeline displays each action's status, timing, arguments, failure reason,
and screenshots. Screenshot paths should be unique and relative to the report.

## Current limitations

- Session collection is caller-managed and synchronous
- No session replay
- No general desktop screenshot capture
- No CLI, dashboard, or recovery system
- The real browser examples are the only current integration
