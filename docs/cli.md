# CLI workflow

Agent DevTools is a library that attaches to an existing agent. It is not a
global background process that can discover every program on the computer.
After the one-time integration, however, the user's workflow can be as simple
as entering a task in a terminal and opening the generated report.

## Browser Use: one-time setup

Install the optional Browser Use integration and Chromium:

```bash
uv add "39-tools[browser-use] @ git+https://github.com/YYDongRo/39-tools.git"
uv run playwright install chromium
```

Set the model provider key in the environment expected by Browser Use. For the
Gemini example in this repository:

```bash
export GOOGLE_API_KEY="..."
```

Do not put the key in `agent_devtools.toml` or in Python source code.

Copy the optional recording configuration once:

```bash
cp agent_devtools.example.toml agent_devtools.toml
```

The file controls recording and output behavior only:

| Setting | Purpose |
| --- | --- |
| `enabled` | turn tracing on or off |
| `screenshots` | capture before-and-after screenshots |
| `redact_sensitive_data` | redact credential-shaped metadata |
| `terminal_summary` | print a short result summary |
| `open_report` | open the report automatically after a local run |
| `trace_directory` | root for individual task traces |
| `evaluation_directory` | root for repeated-run evaluations |

The task and model remain in the Agent creation code. Credentials remain in
environment variables.

## Run a task from the terminal

The included example prompts for a task when `--task` is omitted:

```bash
uv run --extra browser-use python examples/browser_use_cli.py \
  --headed --open-report
```

The user enters a normal request, for example:

```text
Task: Open example.com and confirm the Example Domain page is open.
```

The example creates the Browser Use Agent, wraps it once, runs the task, and
prints the report path. A report is created even when the Agent raises or the
final task verification fails. The command exits non-zero for a failed or
unverified task, which makes it usable in a test script or CI job.

To skip the prompt, pass the task directly:

```bash
uv run --extra browser-use python examples/browser_use_cli.py \
  --task "Open example.com and confirm the Example Domain page is open."
```

The report is normally under `trace/browser-use/`. The exact path is printed
after every run. The report is local and may contain URLs, typed values, and
screenshots; review it before sharing.

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

The callback can later be backed by an LLM, but it is not tied to a provider.
If it fails, Agent DevTools records an `unverified` result with a sanitized
verification note. Configure either `task_verification` or
`final_state_verifier`, not both.

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
