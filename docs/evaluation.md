# Repeated-run stability evaluation

Agent DevTools can run one Browser Use task several times, preserve every
individual trace, and summarize the observed stability in one local HTML
report. Runs are sequential and each attempt uses a fresh Agent. The provided
script defaults to the safe `example.com` demo, but accepts any allowed domain.

## Create an evaluation

```python
from browser_use import Agent, Browser, ChatGoogle
from agent_devtools.browser_use import (
    BrowserUseFinalStateCheck,
    evaluate_browser_use_agent,
)


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
    final_check=BrowserUseFinalStateCheck(
        url_contains="/products/wireless-headphones",
        title_contains="Wireless Headphones",
    ),
)
evaluation.open_report()
```

## Run the provided workflow

For a first real run, use the included product-shaped example. It creates a
fresh Browser Use Agent for each attempt, keeps the individual reports, and
returns exit code `1` when any requested run is failed, unverified, or errored.

```bash
cp agent_devtools.example.toml agent_devtools.toml
# Set GOOGLE_API_KEY in the shell; never put it in the TOML file.
uv run --extra browser-use python examples/browser_use_evaluation.py \
  --runs 3 \
  --allowed-domain example.com \
  --title-contains "Example Domain" \
  --open-report
```

The aggregate report is written below `evaluations/browser-use/` by default.
Set `evaluation_directory` in `agent_devtools.toml` to change that root. The
same `open_report` setting opens the aggregate report after an evaluation;
individual run reports remain linked from it. All output is local unless the
developer explicitly copies or uploads it.

### Compare with the previous evaluation

To make later runs compare automatically, copy the example configuration and
leave this option enabled:

```toml
[agent_devtools]
compare_previous = true
```

The first evaluation of a task has no baseline. The next evaluation with the
exact same task text finds the newest previous result and writes
`comparison.json` and `comparison.html` beside the current `evaluation.json`.
The normal report links to the comparison, which shows pass-rate changes,
new or resolved failure patterns, and average duration/action changes. A
different task is never silently compared.

Metadata redaction is enabled by default. Common credential-shaped keys,
tokens, and URL query values are replaced with `[REDACTED]`; screenshots are
kept as captured and must still be reviewed before sharing.

Use `--headed` when you want to watch the browser. Leave it off for a faster
headless run or CI. A failed evaluation still writes every available trace
before returning the non-zero status.

For a real site, pass one or more `--allowed-domain` values and choose the
smallest useful final check. For example:

```bash
uv run --extra browser-use python examples/browser_use_evaluation.py \
  --config agent_devtools.toml \
  --task "Open YouTube, search for Miku Expo, click the first video, and watch it." \
  --allowed-domain youtube.com \
  --url-contains "youtube.com/watch" \
  --runs 3 --headed --open-report
```

`--url-contains` and `--title-contains` are optional and can be combined. They
are deterministic checks of the final browser state; without either option,
the Browser Use judge supplies the final verification. A URL check can confirm
that YouTube opened a video page, but cannot by itself prove playback duration.

When calling the Python API from a test, use
`evaluation.assert_all_passed()` for the same CI-friendly behavior. The
assertion includes the aggregate report path.

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
When `final_check` is provided, its deterministic result is the final task
verification; the Browser Use judge is retained as supporting evidence.

## Output

```text
evaluations/browser-use/<timestamp>-<id>/
├── evaluation.json
├── report.html
├── comparison.json       # when compare_previous is enabled and a baseline exists
├── comparison.html       # when compare_previous is enabled and a baseline exists
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
