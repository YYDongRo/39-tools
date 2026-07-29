# Agent DevTools

[![Tests](https://github.com/YYDongRo/39-tools/actions/workflows/tests.yml/badge.svg)](https://github.com/YYDongRo/39-tools/actions/workflows/tests.yml)

> **Status:** Early alpha. The current codebase focuses on observable browser
> agent runs; desktop, Android, and arbitrary agent interception are not yet
> supported.

Agent DevTools is an open-source Python library for making computer-use agents
observable, debuggable, and easier to trust.

Wrap a supported agent once, run it normally, and get a local HTML report of
its state-changing actions, what changed, and why the task passed, failed, or
could not be verified.

![Agent DevTools report showing a successful task, action totals, and final checks](docs/assets/report-overview.png)

## What it can do

- Record an ordered trajectory of supported browser actions.
- Capture action arguments, timing, status, and failure details.
- Save before-and-after screenshots and compact page state.
- Separate action execution from action checks and final task verification.
- Surface browser errors, network failures, and repeated no-progress actions.
- Write versioned JSON traces and a standalone HTML report after every
  observed run.

The easiest current integration is
[Browser Use](https://github.com/browser-use/browser-use). Lower-level
Playwright and generic tool wrappers are also available.

Today, the one-time observer experience applies to Browser Use `0.13.x`.
Other agents must use the Playwright or generic tool wrappers, or provide a
dedicated adapter.

## Quickstart: observe a Browser Use agent

Requirements:

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- Git, while installing the early alpha directly from GitHub
- A model provider key supported by Browser Use

The project is not yet published on PyPI. Install the early alpha directly from
this GitHub repository, then install Chromium:

```bash
uv add "39-tools[browser-use] @ git+https://github.com/YYDongRo/39-tools.git"
uv run playwright install chromium
```

The distribution is named `39-tools`; Python imports continue to use
`agent_devtools`.

Keep the provider key in an environment variable. For example, Browser Use's
Google client reads `GOOGLE_API_KEY`:

```bash
export GOOGLE_API_KEY="your-key"
```

Add one import and wrap the existing agent once:

```python
import asyncio

from browser_use import Agent, Browser, ChatGoogle
from agent_devtools.browser_use import observe_browser_use_agent


async def main() -> None:
    task = "Open example.com and confirm the Example Domain page is open."
    browser = Browser(headless=False)

    agent = observe_browser_use_agent(
        Agent(
            task=task,
            llm=ChatGoogle(model="gemini-2.5-flash"),
            browser=browser,
            use_judge=True,
        ),
        task,
    )

    try:
        await agent.run(max_steps=5)
    finally:
        await browser.stop()
        print(f"Report: {agent.last_report_path}")


asyncio.run(main())
```

The agent still receives its normal user task and uses its normal tools. Agent
DevTools connects to the run lifecycle and creates a unique directory under
`trace/browser-use/` containing:

```text
trace/browser-use/<run-id>/
├── session.json
├── report.html
└── actions/
    ├── 001/
    │   ├── before.png
    │   └── after.png
    └── ...
```

At the end of the run, the observer prints a compact result before the full
report is opened:

```text
Agent DevTools
Task: Open example.com and confirm the page is open.
Task result: SUCCESS
Actions: 1 (1 succeeded, 0 failed)
Final check: passed
Report: /path/to/trace/browser-use/<run-id>/report.html
```

Pass `print_summary=False` to `observe_browser_use_agent(...)` when a host
application handles its own console output.

Open the printed `report.html` path in any browser. From WSL, this opens the
latest report directly with the system's default browser:

```python
agent.open_last_report()
```

Opening is explicit, so a normal run or CI job never launches a browser unless
the caller requests it.

Call `agent.assert_last_task_passed()` when a failed or unverified final result
should fail a test.

### Try it from this repository

```bash
uv sync --extra browser-use
uv run --extra browser-use playwright install chromium
export GOOGLE_API_KEY="your-key"
uv run --extra browser-use python examples/browser_use_quickstart.py
```

## What the report tells you

The HTML report leads with the final task result and then shows the action
timeline. It keeps three different questions separate:

1. **Execution:** Did the click, fill, or navigation run successfully?
2. **Action check:** Did that action produce its expected local effect?
3. **Final check:** Did the complete run satisfy the user's task?

A successful action is not automatically proof that the task succeeded. Page
state changes are evidence, while a configured check or agent judge supplies a
verification result.

For each recorded action, the report can include:

- action type, arguments, start time, and duration;
- execution and verification status;
- failure category, likely cause, and bounded diagnostic evidence;
- URL and structured state changes;
- browser, console, request, and HTTP error evidence;
- before-and-after screenshots.

## Other ways to integrate

| Integration | Best for | Entry point |
| --- | --- | --- |
| Browser Use observer | Existing Browser Use agents | `observe_browser_use_agent(...)` |
| Playwright agent observer | Agents with `run(user_request, *, tools=...)` | `observe_playwright_agent(...)` |
| Playwright tool wrapper | Existing browser tool objects | `record_playwright_tools(...)` |
| Generic sync/async wrapper | Framework-independent tool objects | `record_tools(...)`, `record_async_tools(...)` |
| Core recorder | Building a custom adapter | `SessionRecorder`, `record_action(...)` |

See the detailed guides:

- [Browser Use integration](docs/browser-use.md)
- [Playwright and tool integrations](docs/playwright.md)
- [Results, verification, and trace concepts](docs/concepts.md)
- [Development and testing](docs/development.md)

## Current scope

Agent DevTools currently focuses on browser-based agents. It records calls that
pass through a supported observer or wrapped tool object; it cannot intercept
arbitrary direct browser, desktop, or Android operations.

The Browser Use timeline intentionally omits read-only operations such as
screenshots, extraction, state reads, and `done`. It does not record hidden
model reasoning.

Current limitations include:

- no general desktop or Android recorder;
- no dashboard or hosted trace service;
- no general session replay or automatic recovery;
- sequential async action recording only;
- AI-assisted verification is probabilistic and is not ground truth.

The project plan is available in [PROJECT_PLAN.md](PROJECT_PLAN.md).

## Privacy

Traces stay local by default, but they may contain URLs, typed arguments, page
titles, screenshots, visible text, and bounded error details. Keep trace
directories private until they have been reviewed or redacted. Provider keys
are read from environment variables and are not written to reports.

## Development

```bash
uv sync
uv run pytest
```

Browser integration tests and examples use optional dependency groups. See
[the development guide](docs/development.md) for the commands and compatibility
notes.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and pull-request
guidance. Report vulnerabilities and review trace-safety guidance in
[SECURITY.md](SECURITY.md).

## License

Agent DevTools is available under the [MIT License](LICENSE).
