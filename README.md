# Agent DevTools

[![Tests](https://github.com/YYDongRo/39-tools/actions/workflows/tests.yml/badge.svg)](https://github.com/YYDongRo/39-tools/actions/workflows/tests.yml)

**Action-level visual debugging and task reliability evaluation for Browser Use
and Playwright agents.**

![Agent DevTools report showing a successful task, action totals, and final checks](docs/assets/report-overview.png)

Agent DevTools observes an existing agent and writes a local JSON trace plus a
readable HTML report. It helps answer:

- What did the agent ask the computer to do?
- What changed before and after each action?
- Did the action execute, and if not, why?
- Did the complete task succeed?
- Does the same task fail repeatedly?

The displayed project name is **Agent DevTools**. The Python distribution is
`39-tools`, and Python imports use `agent_devtools`.

The package is an alpha and is not yet published on PyPI. For a reproducible
install, use the fixed `v0.1.0` GitHub release or a repository checkout.

## See a report first

You can inspect a committed failure report without installing anything or using
an API key:

- [Sample action report](docs/sample-report/report.html): actions execute, but
  the wrong product is opened and the final task check fails.
- [Sample stability report](docs/sample-evaluation/report.html): six
  deterministic attempts with passes, repeated wrong-target failures, and an
  unverified run.

These artifacts are generated with the same project models and report writers
used by real runs.

## Try a real local browser (no API key)

This deterministic demo uses a local page and Playwright-managed Chromium. It
does not contact a model or the network:

```bash
uv sync --extra browser
uv run --extra browser playwright install chromium
uv run --extra browser python examples/generic_agent_browser.py \
  --headed --open-report
```

The command records a navigation and click, verifies the final page, and prints
the report path. Remove `--headed` for a headless run. Reports are written below
`trace/generic-agent-browser/`.

## Run your Browser Use agent

The supported Browser Use workflow needs one provider key, kept in your shell
or normal secret store—not in source code or `agent_devtools.toml`.

From a repository checkout:

```bash
uv sync --extra browser-use
uv run --extra browser-use playwright install chromium
```

The supported baseline is Python 3.11–3.14, Browser Use 0.13.x, and Playwright
1.61 or newer.

Set one provider key. Use the equivalent PowerShell syntax on Windows:

```bash
export GOOGLE_API_KEY="your-key-from-Google"
# Or: export OPENAI_API_KEY="your-key-from-OpenAI"
# PowerShell: $env:GOOGLE_API_KEY = "your-key-from-Google"
```

Then run a task. The CLI asks for the task if `--task` is omitted, wraps the
Browser Use agent once, and prints the exact report path:

```bash
uv run --extra browser-use agent-devtools \
  --task "Open example.com and confirm the Example Domain page is open." \
  --headed --open-report
```

The command exits non-zero when the agent errors or the final task is failed or
unverified. Copy `agent_devtools.example.toml` to
`agent_devtools.toml` only when you want persistent recording settings such as
screenshots, report opening, output directories, or an installed Brave/Chrome/
Edge executable. See the [CLI guide](docs/cli.md) for platform-specific paths.
On WSL, `--open-report` tries the Windows default browser automatically.

If the model provider stops early, the terminal summary and report call out the
known cause—such as a rate limit or rejected credentials—separately from the
recorded action results. The run remains `unverified`; the tool does not retry
silently.

To measure the same task across fresh agents, add `--runs N`:

```bash
uv run --extra browser-use agent-devtools \
  --task "Open example.com and confirm the Example Domain page is open." \
  --runs 3 --headed --open-report
```

The default `--runs 1` remains a normal single report. With more than one run,
the command prints an aggregate stability report and keeps one linked report
per attempt. Enable `compare_previous = true` in `agent_devtools.toml` to
compare a later evaluation with the newest result for the exact same task.

For a Python application that already creates its own Browser Use agent, wrap
it once at the run boundary:

```python
from agent_devtools.browser_use import observe_browser_use_agent

raw_agent = create_your_browser_use_agent()
agent = observe_browser_use_agent(raw_agent)
await agent.run(max_steps=10)
print(agent.last_report_path)
```

The observer reads the task from `raw_agent.task`, so the developer does not
enter it a second time. The complete integration contract, cleanup guidance,
and optional deterministic final checks are in the
[Browser Use guide](docs/browser-use.md).

For a custom desktop agent that keeps its tools on `raw_agent.tools`, pass
`tools_attribute="tools"` when wrapping it. Agent DevTools temporarily replaces
that dispatcher with the recording proxy and restores it after the run; the
agent does not need recording code in every action method.

## What the report means

The report deliberately keeps three results separate:

| Result | Question | Example |
| --- | --- | --- |
| Execution | Did the operation run? | A click completed or timed out. |
| Action check | Did this action produce its local effect? | A Browser Use navigation ended on the requested host. |
| Final task check | Did the whole request succeed? | The correct product page is open. |

For Browser Use, successful HTTP/HTTPS `navigate` actions receive an automatic,
tolerant hostname check. It allows normal path/query redirects; a different
host is an action-verification failure, and a missing or non-HTTP URL remains
unverified. This local check does not prove that the correct product or page
content was selected—the final task check remains responsible for that.

## When one run is not enough

The repository includes repeated-run Browser Use evaluation. It creates a fresh
Agent for every attempt, preserves each normal trace, and produces an aggregate
report with pass/fail/unverified/errored counts, repeated failure patterns, and
the earliest useful trajectory difference:

```python
from agent_devtools.browser_use import evaluate_browser_use_agent

evaluation = await evaluate_browser_use_agent(
    agent_factory=create_agent,
    task="Find the wireless headphones and open the correct product page.",
    runs=10,
    max_steps=15,
)
evaluation.open_report()
```

See the [stability evaluation guide](docs/evaluation.md) for the factory
contract, output layout, statistics, and limitations. A short machine-readable
`--summary-json` file is also available for local scripts and CI; it does not
replace the detailed HTML report. For known Browser Use provider interruptions,
the single-run summary also includes a stable issue code and next-step hint
while keeping the run `unverified`. Repeated evaluations carry the same
`issue_code` into each run in `evaluation.json` and count provider interruptions
separately from agent trajectory failures.

To compare future evaluations automatically, set
`compare_previous = true` in the copied `agent_devtools.toml`. The first run
has no baseline; later runs with the exact same task create a concise
`comparison.html` and `comparison.json` beside the current evaluation.

## Other integrations

For an existing Playwright or custom agent, use the observer that matches its
run boundary. The adapter records calls routed through the provided tool object;
it cannot intercept arbitrary direct `page.click()`, `pyautogui`, desktop, or
Android calls.

```python
from agent_devtools import observe_agent

observed = observe_agent(raw_agent, tools, "trace/my-agent")
observed.run(user_request)
print(observed.last_report_path)
```

If a report says **No browser actions captured**, the run did not exercise the
recording boundary. Check the integration before treating the task result as
fully observed; direct browser, desktop, or Android calls may be outside the
observer.

For CI or strict local checks, set `require_recorded_actions = true` in
`agent_devtools.toml`. A successful-looking run with zero captured browser
actions is then marked `unverified` and the CLI exits non-zero. The default is
`false` for compatibility with tasks that can finish without browser actions.

Before a first real run, use `--preflight` to check the observer connection and
trace directory without executing the task or calling the model:

```bash
uv run --extra browser-use agent-devtools \
  --task "Open example.com" --preflight
```

See the [CLI and custom-agent guide](docs/cli.md) and the
[Playwright guide](docs/playwright.md) for the supported contracts. Optional
BYOK trajectory judging is described in the [concepts guide](docs/concepts.md).

## Scope and privacy

Agent DevTools is an early alpha focused on local Browser Use and Playwright
workflows. It is an observer and debugger, not a general-purpose computer-use
agent. It does not currently provide universal desktop/Android interception, a
hosted dashboard, shared trace storage, full replay, or automatic recovery.

Traces remain local by default but may contain URLs, typed values, page titles,
visible text, screenshots, and bounded error details. Review traces before
sharing them. Provider keys are read from environment variables and are not
written to reports.

## Development

```bash
uv sync
uv run pytest
uv build
```

See the [development guide](docs/development.md),
[release checklist](docs/release-checklist.md),
[PROJECT_PLAN.md](PROJECT_PLAN.md), [CONTRIBUTING.md](CONTRIBUTING.md), and
[SECURITY.md](SECURITY.md) for complete project and contribution details.

Agent DevTools is available under the [MIT License](LICENSE).
