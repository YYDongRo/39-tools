# Agent DevTools

[![Tests](https://github.com/YYDongRo/39-tools/actions/workflows/tests.yml/badge.svg)](https://github.com/YYDongRo/39-tools/actions/workflows/tests.yml)

> Action-level visual debugging and task reliability evaluation for Browser Use
> and Playwright agents.

![Agent DevTools report showing a successful task, action totals, and final checks](docs/assets/report-overview.png)

Agent DevTools observes an existing agent and creates a local JSON trace and HTML
report. It helps you see:

- what changed before and after each supported action;
- why an action failed, with its error and evidence;
- whether the complete task succeeded, separately from action execution.

## See a report first

No API key or agent is needed for these committed examples:

- [Sample failure report](docs/sample-report/report.html)
- [Sample stability report](docs/sample-evaluation/report.html)

## Run a Browser Use task

The current alpha is installed from the repository; it is not on PyPI yet.

```bash
git clone https://github.com/YYDongRo/39-tools.git
cd 39-tools
uv sync --extra browser-use
uv run playwright install chromium
```

Set one provider key in your shell, never in source code:

```bash
export GOOGLE_API_KEY="your-key"       # Gemini
# export OPENAI_API_KEY="your-key"     # OpenAI instead
```

PowerShell: `$env:GOOGLE_API_KEY = "your-key"`

Run a task and open its report:

```bash
uv run agent-devtools \
  --task "Open https://example.com and confirm the Example Domain page is open." \
  --headed --open-report
```

Omit `--headed` for headless mode, or omit `--task` to enter it interactively.
The command prints the exact report path.

## Use the local control center

```bash
uv run agent-devtools dashboard --open
```

The local page lets you run a Browser Use task, connect your own compatible
agent, check setup, and open all reports. It also shows the latest result and a
local `Connected` heartbeat when a wrapped Agent is writing to the selected
trace folder. It does not intercept arbitrary desktop calls or upload data.

## Connect your own agent

Wrap your agent once at the run boundary. Calls through its tool dispatcher are
recorded automatically:

```python
from agent_devtools import observe_agent

raw_agent = MyAgent(tools=MyTools())
agent = observe_agent(
    raw_agent, raw_agent.tools, "trace/my-agent", tools_attribute="tools"
)
agent.run(user_request)
print(agent.last_report_path)
```

The agent must route computer actions through that dispatcher, such as
`click`, `type_text`, or `scroll`. Direct calls that bypass it are outside the
recording boundary. See the [custom-agent guide](docs/cli.md#custom-tool-bound-browser-or-desktop-style-agents).

For an agent you create with Browser Use, use
[`observe_browser_use_agent`](docs/browser-use.md). For Playwright, use the
[Playwright adapter](docs/playwright.md).

## Check stability

Run the same Browser Use task with fresh agents:

```bash
uv run agent-devtools \
  --task "Open https://example.com and confirm the Example Domain page is open." \
  --runs 3 --headed --open-report
```

The aggregate report links to every attempt and highlights the earliest useful
trajectory difference. A small observed pass rate describes those runs; it does
not prove true reliability. See the [stability guide](docs/evaluation.md).

## Read the report

| Field | Question |
| --- | --- |
| Execution | Did this operation run or raise an error? |
| Action check | Did this action produce its expected local effect? |
| Task check | Did the complete user request succeed? |

`Passed`, `Failed`, `Unverified`, and `Errored` are different outcomes on
purpose. Traces and screenshots stay local by default and may contain URLs,
typed values, page text, or private screen content. Review them before sharing;
the [CLI guide](docs/cli.md) covers export and redaction.

## Scope and documentation

Agent DevTools supports Browser Use, Playwright, and compatible tool-bound
agents. It is not an agent runtime, universal desktop/Android interceptor,
hosted dashboard, full replay system, or automatic recovery service.

- [Browser Use](docs/browser-use.md) · [CLI and custom agents](docs/cli.md)
- [Playwright](docs/playwright.md) · [Concepts and BYOK judging](docs/concepts.md)
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

Displayed name: **Agent DevTools** · distribution: `39-tools` · Python import:
`agent_devtools` · command: `agent-devtools`.

## Development

```bash
uv sync
uv run pytest
uv build
```

Agent DevTools is available under the [MIT License](LICENSE).
