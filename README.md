# Agent DevTools

Agent DevTools is an open-source Python library for making computer-use agents
observable, debuggable, and easier to trust.

Wrap an agent once, run it normally, and get a local HTML report of what it did,
what changed, and why the task passed, failed, or could not be verified.

![Agent DevTools report showing a successful task, action totals, and final checks](docs/assets/report-overview.png)

## What it can do

- Record an ordered trajectory of browser actions.
- Capture action arguments, timing, status, and failure details.
- Save before-and-after screenshots and compact page state.
- Separate action execution from action checks and final task verification.
- Surface browser errors, network failures, and repeated no-progress actions.
- Write versioned JSON traces and a standalone HTML report after every run.

The easiest current integration is
[Browser Use](https://github.com/browser-use/browser-use). Lower-level
Playwright and generic tool wrappers are also available.

## Quickstart: observe a Browser Use agent

Requirements:

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- A model provider key supported by Browser Use

After Agent DevTools is published, install the Browser Use integration and
Chromium:

```bash
uv add "agent-devtools[browser-use]"
uv run playwright install chromium
```

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

Open the printed `report.html` path in any browser. From WSL, this opens the
trace directory in Windows Explorer:

```bash
explorer.exe "$(wslpath -w "$PWD/trace/browser-use")"
```

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

## License

Agent DevTools is available under the [MIT License](LICENSE).
