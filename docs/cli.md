# CLI workflow

Agent DevTools is a library that attaches to an existing agent. It is not a
global background process that can discover every program on the computer.
After the one-time integration, however, the user's workflow can be as simple
as entering a task in a terminal and opening the generated report.

## First run: real Chromium without an API key

Start here if you want to see the recording and report before connecting your
own agent. From a clone of the repository, run:

```bash
uv sync --extra browser
uv run --extra browser playwright install chromium
uv run --extra browser python examples/generic_agent_browser.py \
  --headed --open-report
```

This deterministic demo uses the local `examples/browser_click.html` page. It
records a navigation and click, captures the before/after evidence, verifies
the final page, and opens the report. It does not need a model, API key, or
network access. Reports are written below `trace/generic-agent-browser/`.

After this run succeeds, choose the Browser Use or custom-agent setup below.

Before spending an API request on a real task, you can check the Browser Use
connection and local output setup without running the agent:

```bash
uv run --extra browser-use agent-devtools \
  --task "Open example.com" \
  --preflight
```

Preflight checks the agent contract, recording hook, browser executable,
trace-directory writability, and screenshot setting. It does not call the
model, launch a browser page, or create a task report. It still needs the same
provider key so the CLI can construct the configured Browser Use agent. A
failed preflight exits non-zero with the failing check and a repair hint.

## Browser Use: one-time setup

Install the optional Browser Use integration and Chromium:

```bash
uv add "39-tools[browser-use] @ git+https://github.com/YYDongRo/39-tools.git@v0.1.0"
uv run playwright install chromium
uv run agent-devtools --help
```

Set exactly one model provider key in the environment. The included CLI
supports Gemini and OpenAI:

```bash
export GOOGLE_API_KEY="..."       # Gemini
# export OPENAI_API_KEY="..."     # OpenAI instead
```

Do not put the key in `agent_devtools.toml` or in Python source code.

Copy the optional recording configuration once:

```bash
cp agent_devtools.example.toml agent_devtools.toml
```

The file controls recording, output, and optional browser selection:

| Setting | Purpose |
| --- | --- |
| `enabled` | turn tracing on or off |
| `screenshots` | capture before-and-after screenshots |
| `redact_sensitive_data` | redact credential-shaped metadata |
| `require_recorded_actions` | mark zero-action runs unverified and fail the CLI |
| `terminal_summary` | print a short result summary |
| `open_report` | open the report automatically after a local run |
| `compare_previous` | compare repeated evaluations with the latest same-task result |
| `trace_directory` | root for individual task traces |
| `evaluation_directory` | root for repeated-run evaluations |
| `browser.executable_path` | optional installed Brave/Chrome/Edge executable |

The task and model remain in the Agent creation code. Credentials remain in
environment variables.

### Choose the browser

The default is Playwright's managed Chromium. It is the easiest option for a
repeatable first run and does not use your personal browser profile. To run
the included Browser Use examples with an installed Brave, Chrome, or Edge,
add this optional section to `agent_devtools.toml`:

```toml
[agent_devtools.browser]
executable_path = "C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe"
```

Use a path that exists in the environment where the command runs. For Linux,
an example is `/usr/bin/brave-browser`; for WSL, use a browser executable
available to the WSL runtime rather than copying a Windows path blindly. The
path selects the browser binary only; it does not select or reuse a personal
browser profile. Remove the section to return to managed Chromium.

To keep separate settings for different environments, pass a configuration
file explicitly. The default is still `agent_devtools.toml` when that file is
present:

```bash
uv run --extra browser-use agent-devtools \
  --config agent_devtools.windows.toml \
  --headed --open-report
```

For example, keep a Windows Brave file and a WSL Chromium file side by side.
Files matching `agent_devtools.*.toml` are ignored by Git so machine-specific
browser paths are not committed.

## Run a task from the terminal

The included example prompts for a task when `--task` is omitted:

```bash
uv run --extra browser-use agent-devtools \
  --headed --open-report
```

When the package is installed into an application or tool environment, run
`agent-devtools` directly. The `examples/browser_use_cli.py` file remains a
compatibility wrapper for source checkouts.

With exactly one supported key set, the CLI selects that provider. If both are
set, choose one explicitly with `--provider gemini` or `--provider openai`.
Use `--model MODEL` to override the provider default.

The user enters a normal request, for example:

```text
Task: Open example.com and confirm the Example Domain page is open.
```

The example creates the Browser Use Agent, wraps it once, runs the task, and
prints one concise summary with the task result, action counts, final check,
and report path. A report is created even when the Agent raises or the final
task verification fails. The command exits non-zero for a failed or
unverified task, which makes it usable in a test script or CI job.

### Check stability with repeated runs

Use `--runs N` when one attempt is not enough. The default `--runs 1` keeps the
single-run workflow above. With a value greater than one, the CLI creates a
fresh Browser Use Agent for each sequential attempt and writes one aggregate
evaluation report plus a normal report for every attempt:

```bash
uv run --extra browser-use agent-devtools \
  --task "Open example.com and confirm the Example Domain page is open." \
  --runs 3 --headed --open-report
```

The terminal prints the evaluation JSON path and aggregate HTML report path.
Each run is classified as `passed`, `failed`, `unverified`, or `errored` using
explicit final verification. If `compare_previous = true` is enabled in the
TOML file, a later evaluation of the exact same task also receives
`comparison.json` and `comparison.html`. The command exits non-zero unless all
requested runs are explicitly passed.

For a stable machine-readable CI handoff, add `--summary-json`:

```bash
uv run --extra browser-use agent-devtools \
  --task "Open example.com and confirm the Example Domain page is open." \
  --summary-json ci/agent-devtools-summary.json
```

This writes a small schema-versioned JSON file with `status` (`passed`,
`failed`, `unverified`, or `errored`), action counts, final-check status, and
local paths to the full HTML report and `session.json`. The detailed report is
still generated for debugging. With `--runs N`, the same option writes the
evaluation counts, empirical pass rate, and paths to `evaluation.json` and the
aggregate report instead. Error summaries include only the exception type, not
the raw message or provider credentials. For a known Browser Use provider
interruption, single-run summaries also include `issue_code`,
`issue_title`, and `issue_next_step`; these fields are `null` when the run has
no classified provider issue. The task remains `unverified`—the diagnostic
code explains why verification was unavailable, not that the task passed.
For repeated evaluations, the summary also includes `issue_code_counts`, and
each run in `evaluation.json` stores its optional `issue_code`. These fields let
scripts separate provider interruptions from Agent trajectory failures.

To skip the prompt, pass the task directly:

```bash
uv run --extra browser-use agent-devtools \
  --task "Open example.com and confirm the Example Domain page is open."
```

The report is normally under `trace/browser-use/`. The exact path is printed
after every run. The report is local and may contain URLs, typed values, and
screenshots; review it before sharing. In WSL, `--open-report` tries
`explorer.exe` first, then falls back to the WSL HTML handler.

After a completed run, the CLI also updates `trace/browser-use/index.html`.
This local index lists recent task reports, statuses, and exported bundles:

```bash
uv run --extra browser-use agent-devtools \
  --task "Open example.com and confirm the Example Domain page is open." \
  --open-index
```

Use `--open-index` only when you want the index opened automatically; the index
is still updated after normal runs without that flag.

### Watch a run locally

The run index is useful after a task finishes. To see whether the current
observer is active while a task is running, start the local control center in a
second terminal:

```bash
uv run --extra browser-use agent-devtools dashboard --open
```

The home page has three paths: **Start a task**, **Setup & health**, and
**Report index**. After a run, **Latest run** shows the status, task, and report
link; **Recent runs** keeps the five newest report links. The page refreshes
while an agent is tracking, reports open in a separate browser tab, and no
trace is uploaded. The server binds to `127.0.0.1` by default, serves only the
selected trace workspace, and stops with `Ctrl+C`. Use `--root PATH` for a
different workspace. Setup & health checks recording, provider environment,
browser, trace directory, screenshots, and redaction without displaying secret
values. If the configuration file has a different name or location, pass it
when starting the dashboard:

```bash
uv run --extra browser-use agent-devtools dashboard \
  --config path/to/agent_devtools.toml --open
```

The dashboard's **Start a task** link is a local shortcut for the same Browser
Use CLI. Enter a task and submit; the dashboard stays available while the
normal trace and report are written. **Runs**, **Maximum steps**, and
**Open a visible browser window** are available under the collapsed
**Advanced settings** section. The form accepts only a task description, never
a shell command, and is disabled when the server is bound to a non-loopback
interface.

### Export a diagnostic bundle

Add `--export-bundle` when you want one offline zip containing the completed
trace, report, screenshots, and a `manifest.json`:

```bash
uv run --extra browser-use agent-devtools \
  --task "Open example.com and confirm the Example Domain page is open." \
  --export-bundle
```

Bundles are written beside the trace root in `bundles/` and use a short,
dated name such as `agent-devtools-20260809-test001.zip`. The UTC date is
followed by a per-day export number; another export that day becomes
`test002`, while the next day starts at `test001`. The archive contains only
relative paths and never includes the source directory name in its manifest.
It is still a copy of local evidence, not an automatic redaction tool: check
task text, arguments, URLs, typed values, and screenshots before sharing.

For a shareable copy, add `--redact`:

```bash
uv run --extra browser-use agent-devtools \
  --task "Open example.com and confirm the Example Domain page is open." \
  --export-bundle --redact
```

The redacted bundle replaces common secret-shaped values in JSON, HTML, and
text files, removes image files, and adds a visible note where screenshots were
referenced. The original trace remains unchanged. This is a conservative,
pattern-based filter; inspect the result before sharing because it cannot
recognize every private value or sensitive detail inside arbitrary images.

## Custom desktop or browser agents

For an agent that is not Browser Use, use the generic observer at the agent's
run boundary:

```python
from agent_devtools import observe_agent

raw_agent = MyAgent()
observed_agent = observe_agent(
    raw_agent,
    MyTools(),
    "trace/my-agent",
    capture_screenshot=capture_screenshot,
)

observed_agent.run(user_request)
print(observed_agent.last_report_path)
```

The agent must accept the recording proxy through this contract:

```python
def run(self, task: str, *, tools: MyTools):
    tools.click(...)
    tools.type_text(...)
```

Agent DevTools wraps public callable methods on `tools` and records their
names, arguments, timing, status, and exceptions. A screenshot callback and a
small state observer are optional but provide stronger visual evidence.

If the agent already owns its dispatcher, it can keep a normal `run(task)`
method. Bind the proxy to that attribute for the duration of the run:

```python
raw_agent = MyAgent(tools=MyTools())
observed_agent = observe_agent(
    raw_agent,
    raw_agent.tools,
    "trace/my-agent",
    tools_attribute="tools",
)
observed_agent.run(user_request)
```

The original `raw_agent.tools` object is restored after the run. This is useful
when the agent's central dispatcher calls `click`, `type_text`, `scroll`, or
other tool methods internally. Calls that bypass that dispatcher and invoke an
unwrapped API directly are still outside the recording boundary.

For automatic final verification, replace `task_verification` with a
`final_state_verifier` callback. It receives a `FinalStateObservation` with the
task, final state, actions, and last after-screenshot path:

```python
from agent_devtools import FinalStateObservation, VerificationResult


def judge(observation: FinalStateObservation) -> VerificationResult:
    passed = observation.state.get("status") == "complete"
    return VerificationResult(
        expected_state="status is complete",
        observed_state=str(observation.state),
        passed=passed,
        failure_reason=None if passed else "the final status is not complete",
    )
```

If it fails, Agent DevTools records an `unverified` result with a sanitized
verification note. Configure either `task_verification` or
`final_state_verifier`, not both.

For a provider-backed check that infers the expected result from the task and
reviews every recorded action in one request, configure a BYOK provider once:

```bash
export AGENT_DEVTOOLS_LLM_PROVIDER=openai
export OPENAI_API_KEY="your-key-from-the-provider"
# Or: export AGENT_DEVTOOLS_LLM_PROVIDER=gemini
#     export GEMINI_API_KEY="your-key-from-the-provider"
```

Use the environment-backed judge at the same one-time wrapper setup:

```python
from agent_devtools import observe_agent, trajectory_judge_from_env

observed_agent = observe_agent(
    raw_agent,
    MyTools(),
    "trace/my-agent",
    observe_state=observe_state,
    trajectory_verifier=trajectory_judge_from_env(),
)
```

The judge sees the task, structured action evidence, and final state. It writes
one action verification per recorded action and one final task result. The
provider SDK reads the key from the environment; Agent DevTools does not store
it. Action arguments and structured state are sent to the provider, while
screenshots stay local in this version. Missing credentials, provider errors,
or uncertain evidence remain `unverified`.

This is an explicit integration boundary. Direct calls such as
`pyautogui.click(...)` made outside `tools` are not automatically visible.
The application can still keep its existing CLI: it only needs to pass the
user's input to `observed_agent.run(user_request)` after the one-time setup.

To understand this contract without installing a browser or connecting a real
desktop, run the deterministic in-memory example:

```bash
uv run python examples/generic_agent.py
```

The example opens an in-memory Settings screen and clicks the wrong toggle by
default. The report therefore shows two successful actions beside a failed
final task check. Run it with `--correct` to see the passing result. It is a
safe contract example, not an automatic desktop controller.

## What the user sees

```text
enter task
    -> agent executes normally
    -> Agent DevTools records each wrapped action
    -> report.html is written
    -> terminal prints the report path
```

Agent DevTools does not start a separate service or silently take control of
the desktop. It records the execution inside the process that runs the Agent.
