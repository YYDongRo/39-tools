# Browser Use integration

Agent DevTools provides action-level visual debugging and task verification for
existing Browser Use agents. Connect the observer once; normal `agent.run(...)`
calls then create a new trace and HTML report automatically.

## Install

The early alpha is not yet published on PyPI. Install it directly from GitHub:

```bash
uv add "39-tools[browser-use] @ git+https://github.com/YYDongRo/39-tools.git"
uv run playwright install chromium
```

The distribution is named `39-tools`; Python imports continue to use
`agent_devtools`.

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

raw_agent = Agent(
    task=task,
    llm=ChatGoogle(model="gemini-2.5-flash"),
    browser=browser,
    use_judge=True,
)
agent = observe_browser_use_agent(raw_agent)

try:
    await agent.run(max_steps=5)
finally:
    await browser.stop()

print(agent.last_report_path)
```

Open the latest report with the system's default browser when running locally:

```python
agent.open_last_report()
```

The method is explicit and is never called automatically in CI. It raises a
clear error if the agent has not run, the report was removed, or the system
cannot launch a browser.

`observe_browser_use_agent(...)` returns an `ObservedBrowserUseAgent`. It reads
the task from `agent.task`, so the developer enters the user's request only
once. It forwards unknown attributes to the original agent, and `run(...)`
returns the original Browser Use result. For compatible agents that do not
expose `task`, pass the goal explicitly as the second argument.

Pass an output directory when the default `trace/browser-use/` is not suitable:

```python
agent = observe_browser_use_agent(raw_agent, output_root=Path("trace/my-agent"))
```

Every run uses a new child directory, so an earlier report is not overwritten.

After a run, the observer prints a short terminal summary containing the task
result, execution totals, final-check status, the first failed action or
verification reason when relevant, and the absolute report path. Detailed
arguments and raw errors remain in the HTML report. Disable this output when a
host application provides its own logging:

```python
agent = observe_browser_use_agent(raw_agent, print_summary=False)
```

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

Browser Use planning and file operations such as `write_file` and
`replace_file` are recorded separately as collapsed auxiliary events. They do
not inflate the browser action count, but remain available in `session.json`
and the report for debugging.

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

### Optional deterministic final checks

The Browser Use judge is useful, but it is still model-based. For a stable
final result, provide bounded checks over the final URL or page title:

```python
from agent_devtools.browser_use import BrowserUseFinalStateCheck

agent = observe_browser_use_agent(
    raw_agent,
    final_check=BrowserUseFinalStateCheck(
        url_contains="/products/wireless-headphones",
        title_contains="Wireless Headphones",
    ),
)
```

The deterministic checks become the report's final result. The Browser Use
judge remains available under collapsed verification evidence, so a disagreement
is visible without making the main report noisy. The check is optional; without
it, the existing Browser Use judge behavior is unchanged. Custom synchronous or
asynchronous checks may also be supplied when URL and title are insufficient;
they receive the bounded final state dictionary and must return a
`VerificationResult`.

When the wrapped Agent uses `use_judge=True`, Browser Use already evaluates the
task supplied to `Agent(task=...)`. Agent DevTools reuses that judgment instead
of asking the developer to repeat the task or making a second LLM request.

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

For repeated stability evaluation, use `evaluate_browser_use_agent(...)`
instead of manually reusing this wrapper. That evaluator requires a factory
that returns a fresh Agent for every attempt and owns each returned Agent's
`close()` lifecycle. See [Repeated-run stability evaluation](evaluation.md).

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
