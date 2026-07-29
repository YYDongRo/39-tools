# Browser Use integration

The Browser Use observer is the recommended high-level integration for an
existing Browser Use agent. It connects recording to the agent once; normal
`agent.run(...)` calls then create a new trace and HTML report automatically.

## Install

After Agent DevTools is published:

```bash
uv add "agent-devtools[browser-use]"
uv run playwright install chromium
```

From this repository:

```bash
uv sync --extra browser-use
uv run --extra browser-use playwright install chromium
```

Keep model provider credentials in the environment variables supported by
Browser Use. Do not pass credentials to Agent DevTools or put them in source
code.

## Wrap an agent

```python
from pathlib import Path

from browser_use import Agent, Browser, ChatGoogle
from agent_devtools.browser_use import observe_browser_use_agent

task = "Open example.com and confirm the page is open."
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

print(agent.last_report_path)
```

`observe_browser_use_agent(...)` returns an `ObservedBrowserUseAgent`. It
forwards unknown attributes to the original agent, and `run(...)` returns the
original Browser Use result.

Pass an output directory when the default `trace/browser-use/` is not suitable:

```python
agent = observe_browser_use_agent(raw_agent, task, Path("trace/my-agent"))
```

Every run uses a new child directory, so an earlier report is not overwritten.

## What is recorded

The integration records one state-changing action per Browser Use step. For
each action it can preserve:

- the action name and JSON-safe arguments;
- start time, duration, and execution status;
- before-and-after screenshots;
- URL, title, and bounded page state;
- Browser Use action errors and results;
- the final Browser Use judge result as task verification.

Read-only operations such as `done`, extraction, screenshots, and state reads
are not added to the state-changing action timeline.

## Verification

Browser Use's judge is mapped to the final task verification. This is separate
from whether individual actions executed successfully:

- a click can execute successfully while the final task still fails;
- a recovered intermediate failure can remain visible while the task passes;
- a run without a usable judge result remains `unverified`.

Use this assertion in a test or CI job:

```python
agent.assert_last_task_passed()
```

It raises `AssertionError` for failed or unverified runs and includes the report
path.

## Lifecycle behavior

The observer preserves existing Browser Use step callbacks and caller-provided
`on_step_end` callbacks. It limits the agent to one state-changing action per
step so before-and-after evidence remains attributable to a single action.

Browser Use can turn a URL in the task into a hidden initial action before the
observer is attached. The integration disables that shortcut and lets the model
perform navigation as a normal recorded action. Explicit caller-provided
`initial_actions` are rejected because they would otherwise execute outside the
observable timeline.

The caller still owns the `Browser` lifecycle and should stop it in `finally`.
If the agent raises, completed actions and a report remain available before the
exception is re-raised.

## Compatibility

The current integration supports Browser Use `0.13.x`. Browser Use `0.13.7`
pins older OpenAI and Google Gen AI SDK versions, so the `browser-use` extra
cannot be installed together with Agent DevTools' `llm-openai` or `llm-gemini`
extras. Use the model clients supplied by Browser Use in this environment.

## Privacy

Reports can contain URLs, action arguments, screenshots, page titles, and
bounded error details. Browser Use may separately send task and page context to
the configured model provider. Review both projects' data policies before using
private applications.
