# Repeated-run stability evaluation

Agent DevTools can run one Browser Use task several times, preserve every
individual trace, and summarize the observed stability in one local HTML
report. Runs are sequential and each attempt uses a fresh Agent.

## Create an evaluation

```python
from browser_use import Agent, Browser, ChatGoogle
from agent_devtools.browser_use import evaluate_browser_use_agent


def create_agent(task: str) -> Agent:
    return Agent(
        task=task,
        llm=ChatGoogle(model="gemini-2.5-flash"),
        browser=Browser(headless=True),
        use_judge=True,
    )


evaluation = await evaluate_browser_use_agent(
    agent_factory=create_agent,
    task="Find the wireless headphones and open the correct product page.",
    runs=10,
    max_steps=15,
)
evaluation.open_report()
```

The factory may be synchronous or asynchronous. It must return a new compatible
Browser Use Agent for every call. The evaluator calls and awaits `close()` on
every returned Agent, including attempts that fail during setup or execution.
Do not reuse a Browser or Agent that another part of the application still
owns.

## Result meanings

| Status | Meaning |
| --- | --- |
| `passed` | Explicit final Browser Use task verification passed. |
| `failed` | Explicit final Browser Use task verification failed. |
| `unverified` | The run ended without usable final task verification. |
| `errored` | Factory, observer setup, agent execution, or cleanup raised an exception. |

An action completing successfully is not enough to classify a run as passed.
Only explicit final task verification produces `passed` or `failed`.

## Output

```text
evaluations/browser-use/<timestamp>-<id>/
├── evaluation.json
├── report.html
└── runs/
    ├── 001/
    │   ├── session.json
    │   ├── report.html
    │   └── actions/
    └── ...
```

Each requested attempt has an inspectable numbered trace. Even a factory error
creates a zero-action session report containing only the error phase and
sanitized exception type. Raw factory, execution, and cleanup exception
messages are not added to the evaluation metadata.

The aggregate report compares unsuccessful trajectories with a representative
successful run. It checks action type, arguments, execution and verification
results, URL, compact state, missing or extra actions, browser/runtime findings,
and final verification. It reports the earliest structured difference it can
explain. Without a successful run, it groups only run-local evidence and says
that no successful baseline was available.

## Statistics and limits

`completed_run_count` excludes errored attempts. Duration and action averages
and medians use completed runs. The empirical pass rate is passed attempts
divided by all requested attempts, so errored and unverified attempts do not
count as passes.

An empirical pass rate over a small sample describes only the observed runs; it
does not prove the agent's true reliability. The evaluator does not add
concurrency, retries, replay, repair, or model-based trajectory comparison.
Traces can contain screenshots, URLs, typed arguments, page titles, and bounded
error evidence, so review them before sharing.

Open the committed [sanitized sample evaluation](sample-evaluation/report.html)
without an API key or agent run. Regenerate it with:

```bash
uv run python examples/generate_sample_evaluation.py
```
