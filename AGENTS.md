# Agent DevTools Development Guide

This repository is building **Agent DevTools**, an open-source, local-first
reliability layer for teams that develop and operate computer-use agents.

The product helps a developer answer, with evidence:

- What did the agent ask the computer to do?
- What changed before and after each action?
- Did the action execute, and if not, why?
- Did the complete user task succeed?
- Does the same task fail in a repeatable way?

The long-term direction is a product that can serve both an individual engineer
and a company team. The current repository is the open-source core and local
workflow, not yet a hosted enterprise service.

## Product boundary

Agent DevTools observes, records, verifies, analyzes, and evaluates an existing
agent. The agent still decides what to do.

This project is not:

- a general-purpose computer-use agent;
- an LLM framework or model-training system;
- a replacement for Browser Use, Playwright, or another agent runtime;
- a universal interceptor for arbitrary browser, desktop, or Android calls;
- a hosted dashboard, trace database, or collaboration service yet.

Do not claim a capability only because it is on the roadmap. Claims must be
supported by source code, tests, and user-facing documentation.

## Product positioning

Keep the message narrow and evidence-based:

> Action-level visual debugging and task reliability evaluation for Browser Use
> and Playwright agents.

The differentiating workflow is failure-oriented debugging, not generic event
collection:

```
run the agent normally
    -> capture action evidence
    -> show before/after state
    -> separate execution from task outcome
    -> compare repeated runs
    -> explain the earliest useful divergence
```

Do not add features merely because another observability product has them. A
new feature should make an agent failure easier to understand, reproduce, or
prevent.

## Users and supported workflows

Design for three user groups:

1. **Individual developers and researchers** who need a local report while
   building an agent.
2. **Agent teams** who need repeatable evaluations, failure patterns, and CI
   gates for task reliability.
3. **Platform and QA engineers** who may eventually need shared storage,
   access control, retention, and integrations across many agent projects.

The current supported workflows are:

1. Wrap a supported Browser Use, Playwright, or contract-compatible agent once.
2. Run its normal task without entering the task a second time when the
   framework exposes it.
3. Inspect the local JSON trace and static HTML report.
4. Optionally run the same Browser Use task with fresh Agents and compare the
   resulting trajectories.
5. Use the explicit evaluation verdict as a local or CI quality gate.

The intended future team workflow adds a secure export or hosted service, but
that is a separate product layer and must not be assumed to exist in the local
package.

## Current implementation (verified in this repository)

### Core observability

- `ActionRecord` and `ActionStatus` store action type, arguments, timing,
  screenshots, execution status, and failure information.
- `ActionSession` and `SessionRecorder` preserve ordered trajectories, goals,
  task verification, final outcomes, and resumable session state.
- Versioned JSON persistence uses safe relative paths and atomic writes.
- Static action and session HTML reports show screenshots, compact state,
  action checks, task checks, and bounded browser/runtime evidence.
- Failure categories cover explicit timeout, operation, verification, and
  unknown signals. Prefer evidence over inferred explanations.

### Integrations

- Playwright supports traced `navigate`, `click`, `fill`, `press`, and
  `scroll` flows plus element diagnostics, state observations, task checks,
  and bounded page/console/network findings.
- Browser Use 0.13.x has an observer that wraps an existing Agent once,
  records state-changing steps, keeps auxiliary planning events collapsed,
  preserves normal callbacks, and maps the framework judge into task evidence.
- Browser Use repeated evaluation creates a fresh Agent per run, retains a
  normal trace for every attempt, computes conservative divergences and failure
  groups, and writes versioned aggregate JSON and static HTML.
- Framework-independent `observe_agent(...)` and
  `observe_async_agent(...)` inject the existing sync/async recording proxies
  into agents with `run(task, *, tools=...)`, or temporarily bind them to an
  existing tool attribute via `tools_attribute`. A caller does not instrument
  each action manually. They also accept an optional provider-neutral
  `final_state_verifier` for task-level judge results.
- The generic observers also accept an optional BYOK `trajectory_verifier`
  (use `trajectory_judge_from_env()` for OpenAI or Gemini) that reviews the
  task, structured action evidence, and final state in one request, attaching
  action-level and task-level results. Provider errors remain `unverified`.
- Optional OpenAI/Gemini expectation and final-state integrations remain
  bounded, provider-specific, and probabilistic. They must not silently
  replace deterministic verification semantics.
- Replay is intentionally limited to validated click and fill actions plus a
  bounded Playwright session-context replay; it is not full session replay or
  recovery. Repeated Playwright replay evaluates the recorded trajectory and
  does not rerun the agent or perform automatic repair.

### User-facing entry points

- Display name: **Agent DevTools**.
- Distribution name: `39-tools`.
- Python import name: `agent_devtools`.
- Browser Use observer: `observe_browser_use_agent(...)`.
- Browser Use setup check: `ObservedBrowserUseAgent.preflight()` and CLI
  `--preflight`.
- Generic agent observer: `observe_agent(...)` and `observe_async_agent(...)`.
- Repeated evaluator: `evaluate_browser_use_agent(...)`.
- Replay stability evaluator: `evaluate_playwright_session_replay(...)`.
- Replay stability reports show a concise first trajectory difference in the
  aggregate table; detailed original/replay values stay collapsed in each run
  report.
- Playwright replay can select the first failed action automatically; if only
  the final task check failed, it clearly labels the last-action fallback.
- Product-shaped example: `examples/browser_use_evaluation.py`.
- CLI task example: `examples/browser_use_cli.py`.
- Deterministic real-browser boundary demo:
  `examples/generic_agent_browser.py`.
- Deterministic no-dependency generic boundary demo:
  `examples/generic_agent.py`.
- Human-readable config: `agent_devtools.toml`, based on
  `agent_devtools.example.toml`.
- CLI and custom-agent setup guide: `docs/cli.md`.
- Local control center: `agent-devtools dashboard --open`; its **Start a task**
  page launches only the existing Browser Use CLI on loopback, reads the latest
  `run-state.json`, links to local reports, and exposes bounded `runs` and
  `max_steps` settings.

Keep these names stable unless a deliberate compatibility plan is written.

## Architecture

```
Browser Use / Playwright / future agent runtime
                    |
          integration adapter or observer
                    |
          ActionRecord + ActionSession
                    |
       screenshots | JSON trace | HTML report
                    |
       action checks + final task verification
                    |
       failure analysis + repeated-run evaluation
                    |
        local developer/CI result (current)
                    |
       secure exporter / team service (future)
```

Keep framework-specific behavior in `src/agent_devtools/integrations/` and keep
the core models, serialization, analysis, and reports framework-agnostic.

## Result semantics

Never collapse these levels into one boolean:

- **Execution status**: did a particular operation run or raise an error?
- **Action verification**: did that operation produce its expected local effect?
- **Final task outcome**: did the complete trajectory satisfy the request?
- **Evaluation run status**: was one repeated attempt passed, failed,
  unverified, or errored?

Explicit deterministic checks are authoritative for the fields they cover.
LLM judges can provide supporting evidence or hypotheses, but missing context
must remain `unverified`, not be presented as success.

## Privacy and security rules

Treat task text, typed values, arguments, URLs, exception details, and
screenshots as potentially sensitive.

- Never put API keys in source, TOML, tests, reports, or committed examples.
- Keep provider credentials in environment variables or the provider's normal
  secret store.
- Preserve metadata redaction defaults and test common credential-shaped keys,
  tokens, and URL query values when changing Browser Use recording.
- Screenshots are not automatically redacted; documentation must say so.
- Sanitize persisted exception details and avoid storing hidden model reasoning.
- Reject absolute or parent-traversing stored paths where the schema requires
  safe relative paths.
- Do not add uploads, hosted storage, authentication, or team sharing without
  an explicit data-retention and access-control design.

## Open-source core and future company product

Keep the open-source package useful on its own:

- local traces and reports;
- stable schemas and public Python APIs;
- deterministic tests and sample artifacts;
- Browser Use and Playwright adapters;
- CI-friendly machine-readable verdicts.

Treat these as future, separately designed layers rather than hidden coupling
in the core recorder:

- shared project/run storage;
- organization and project boundaries;
- authentication, roles, SSO, and audit logs;
- retention, deletion, encryption, and regional data controls;
- searchable run history and team annotations;
- hosted APIs, dashboards, and enterprise support.

Before implementing a hosted layer, define its ingestion contract, threat
model, retention behavior, and migration path from local JSON. Do not make the
local package require a server or provider account.

## Engineering principles

- Prefer observed evidence over guesses.
- Keep the core model- and framework-agnostic.
- Keep adapters thin and explicit; do not monkey-patch arbitrary runtimes.
- Preserve backward compatibility for saved trace and evaluation schemas where
  practical. Version any incompatible change.
- Keep repeated evaluations sequential and fresh unless concurrency is a
  deliberate, tested feature; do not add hidden retries.
- Use deterministic local pages and fake agents for unit tests.
- Keep optional providers and browser dependencies out of the core install.
- Reuse existing public APIs before adding abstractions.
- Keep reports concise, readable, and useful during failure triage.
- Update README/docs whenever exposed behavior or setup changes.
- Keep generated artifacts deterministic and out of normal temporary output.
- Avoid broad refactors, speculative abstractions, and unrelated UI work.

## Development workflow

For every implementation request:

1. Inspect the repository, relevant docs, current Git status, and existing
   tests.
2. State the smallest plan before editing; communicate with the user in the
   requested language (currently Chinese).
3. Implement one bounded milestone and preserve unrelated local changes.
4. Add focused tests for new behavior, including failure and privacy cases.
5. Run focused tests, then the full suite and build checks appropriate to the
   changed area.
6. Review `git diff --check`, generated paths, and documentation.
7. Report files changed, behavior, commands/results, limitations, and one
   next milestone.

Useful checks from the project root:

```bash
uv run pytest
uv lock --check
uv build
git diff --check
```

Use the project's normal WSL environment when Windows virtual-environment
permissions prevent `uv` from recreating `.venv`. Browser Use and Playwright
integration tests are optional checks when their extras and browsers are
available; core tests must not require API keys or network access.

## Near-term roadmap

Work in this order unless the user explicitly changes direction:

1. **Core contract hardening**: stabilize action/session/evaluation schemas,
   public imports, redaction, reports, and deterministic sample artifacts.
2. **Developer adoption**: keep the first-run flow short, make CI artifacts
   obvious, and validate supported Browser Use/Playwright versions.
3. **Adapter contract**: extend and test the small generic boundary already
   provided by `observe_agent(...)` so new agent runtimes can be added without
   changing the core recorder.
4. **Reliability workflows**: improve divergence evidence, failure grouping,
   and controlled replay only when it answers a concrete debugging need.
5. **Team foundation**: design export, run identity, retention, and access
   boundaries while keeping local mode fully functional.
6. **Optional hosted product**: implement secure shared storage and team UX only
   after the local data contract and privacy model are stable.

Do not jump directly to a hosted dashboard, universal desktop interception,
Android support, full replay, automatic recovery, or model training.

## Definition of done

A change is complete only when:

- the behavior is implemented and reachable through a documented API or
  example;
- focused and existing tests pass;
- generated reports use safe, deterministic paths;
- security/privacy implications are documented;
- no unrelated files or public APIs are changed accidentally;
- the user can understand how to run and inspect the result.

## Commit convention

Use Semantic Commit Messages:

```
<type>(<scope>): <subject>
```

Use concise lowercase subjects. When the user's standing instruction authorizes
automatic local commits, include:

```
Signed-off-by: Roy <157320193+YYDongRo@users.noreply.github.com>
```

Never push automatically; pushing requires a separate explicit request.
