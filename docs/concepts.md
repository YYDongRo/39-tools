# Results, verification, and trace concepts

Agent DevTools separates browser-action evidence from deciding whether the
complete task was correct. This avoids treating "the API call returned" as
proof that the user's goal was satisfied.

## Three result levels

### Execution status

Execution status answers whether a computer action ran without an operation
error. It is `success` or `failure`.

Examples:

- Playwright found the button and completed the click: success.
- The selector timed out or the input was readonly: failure.

### Action verification

An optional action check answers whether that one action produced the expected
local effect. A successful action without a configured check remains
unverified; this is neutral, not an error.

### Final task verification

The final check answers whether the whole trajectory satisfied the user's goal.
The session outcome is:

- `success` when final verification passes;
- `failure` when final verification fails;
- `unverified` when no reliable final verification ran.

Intermediate failures remain visible even if the agent recovered and the final
task passed.

If the agent itself raises during a run, the session remains `unverified`—it is
not a claim that the task failed—but the report marks **Agent run failed** and
stores only the exception type, not the raw exception message.

## Action records

An action record includes:

- action type and JSON-serializable arguments;
- timezone-aware start timestamp and duration in milliseconds;
- execution status and optional failure reason;
- optional screenshot paths before and after;
- conservative failure category and bounded evidence;
- optional structured observations and verification result.

Sessions store actions in execution order with the user goal, final task
verification, and derived outcome. JSON schemas are versioned, and loaders
remain compatible with earlier supported schema versions.

## Evidence is not verification

A URL change, focused element, screenshot, or different scroll position can
explain what happened. It does not by itself establish what should have
happened. Verification requires one of:

- a deterministic developer-supplied check;
- a check derived directly from the action, such as fill value equality or the
  Browser Use navigation-host check;
- a framework judge;
- an optional model assessment grounded in bounded observed state.

For Browser Use, an optional deterministic final-state check can validate URL
and title components independently of the model judge. When configured, that
check determines the final result and the judge remains supporting evidence.

AI verification is probabilistic and should not be treated as ground truth for
high-risk decisions.

## The agent integration boundary

The framework-independent entry points `observe_agent(...)` and
`observe_async_agent(...)` accept an agent with this small contract:

```python
agent.run(task, *, tools=recorded_tools)
```

The observer reads `agent.task` when the task is not passed again, injects a
recording proxy once, and sends every callable tool method through the existing
action/session recorder. Screenshot and state callbacks remain optional. A
`final_state_verifier` can consume a `FinalStateObservation` containing the
task, final state, actions, and last after-screenshot. Agents that call browser
or desktop APIs directly instead of using the provided tool object still
require a framework-specific adapter.

The final-state verifier is an alternative to the deterministic
`task_verification` callback. Its errors are recorded as `unverified`, and it
must never be treated as ground truth merely because it uses an LLM.

For a one-time BYOK setup, `trajectory_judge_from_env()` can be passed as a
`trajectory_verifier`. It sends one bounded request containing the task, all
structured action evidence, and the final state, then attaches one result to
each action and one result to the session. It does not upload screenshots and
does not store provider keys. The provider response is still probabilistic;
missing or uncertain evidence stays `unverified`.

## Failure analysis

Core recording classifies timeouts, operation errors, verification mismatches,
and unknown failures conservatively. Playwright integrations can add direct
element evidence for categories such as:

- `target_not_found`
- `target_ambiguous`
- `target_not_visible`
- `target_disabled`
- `target_not_editable`

The report can also prioritize browser page errors, failed requests, HTTP
errors, and repeated identical actions that produced no observed progress.
Potential issues are warnings; they do not change the task result.

## Persistence and replay

Each session writes `session.json` atomically and regenerates `report.html` as
actions arrive. A non-empty trace directory is never overwritten implicitly.
Interrupted runs retain their completed evidence, and an existing session can
be resumed explicitly.

The framework-independent replay helpers intentionally stay narrow: one saved
synchronous `click` or `fill` action can be replayed through a caller-provided
executor after strict argument validation. Replay is post-run and
developer-triggered; it does not rerun an Agent or retry an action
automatically.

For example, a loaded `fill` record can be replayed without rebuilding the
original agent:

```python
from agent_devtools import replay_fill


def execute_fill(selector, text, timeout_ms):
    locator = page.locator(selector)
    if timeout_ms is None:
        return locator.fill(text)
    return locator.fill(text, timeout=timeout_ms)


result = replay_fill(source_action, execute_fill)
print(result.outcome_matches)
```

To try this against a real local Chromium page, install the browser extra and
run `uv run --extra browser python examples/browser_fill_replay.py`. The script
writes an original session, a replay session, screenshots, and `report.html`
under `trace/browser-fill-replay/`.

For a bounded Playwright session replay, use
`replay_playwright_session_action(...)` with a fresh page. The target action
number is optional: when omitted, Agent DevTools selects the first recorded
failed action. If every action executed but the final task check failed, it
uses the last action as a clearly labelled fallback. It replays the preceding
`navigate`, `click`, `fill`, `press`, or `scroll` actions first, then runs the
target and writes a new session report.
If a context action fails, the target is not run and the report explains where
reconstruction stopped. General trajectory replay and recovery are not
implemented. The replay report also shows a clear `Reproduced` or `Not
reproduced` verdict, with the original and replay target outcomes side by side.

To check whether a result is stable, use
`evaluate_playwright_session_replay(...)`. It calls the bounded session replay
on a fresh page for each requested run. The target action number is optional
here as well, so the common failure-debugging path needs no action counting.
It keeps each run under `runs/001/`,
`runs/002/`, and so on, and writes an aggregate `report.html`. The aggregate
report distinguishes a stable result, an intermittent result, and a result
that was not reproduced. Its run table shows only the first trajectory
difference by default; the linked individual report keeps the original and
replay evidence in a collapsed detail section. The local demo can be run with:

```bash
uv run --extra browser python examples/browser_replay_stability.py
```

Browser Use reports keep planning and file-management operations in a separate
collapsed auxiliary-event section. The main timeline and action statistics only
count browser actions.

## Privacy

Even local debugging evidence can be sensitive. Traces may contain:

- page URLs and titles;
- typed tool arguments;
- screenshots and visible UI content;
- error messages and URL paths;
- bounded state sent to an optional model provider.

Trace directories should be ignored by source control and shared only after
review. Agent DevTools avoids storing provider keys, cookies, browser storage,
headers, and network bodies, but integrations and external agent frameworks may
have their own data behavior.
