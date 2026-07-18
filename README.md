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
- A static HTML report showing action details and screenshots
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

## Current limitations

- Records one synchronous action at a time
- No multi-action sessions or replay
- No general desktop screenshot capture
- No CLI, dashboard, or recovery system
- The HTML report displays one action at a time
- The real browser example is the only current integration
