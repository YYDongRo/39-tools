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
- a check derived directly from the action, such as fill value equality;
- a framework judge;
- an optional model assessment grounded in bounded observed state.

For Browser Use, an optional deterministic final-state check can validate URL
and title components independently of the model judge. When configured, that
check determines the final result and the judge remains supporting evidence.

AI verification is probabilistic and should not be treated as ground truth for
high-risk decisions.

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

Current replay support is intentionally narrow: one saved synchronous click can
be replayed through a caller-provided executor after strict argument validation.
General trajectory replay and recovery are not implemented.

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
