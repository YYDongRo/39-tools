# Project Identity

Agent DevTools is a developer-tooling project for computer-use agents.

Mission:
Make computer-use agents observable, debuggable, verifiable, and eventually replayable.

This project is NOT:

- a general AI agent;
- an LLM framework;
- a coding agent;
- a replacement for OpenClaw, Google ADK, or browser-use;
- a model-training project.

It is an action-level reliability and debugging layer that existing computer-use agents can integrate with.

# Target Users

The main users are engineers and researchers building agents that:

- click;
- type;
- scroll;
- navigate browser or desktop interfaces;
- interact with visual UI state.

The tool should help them answer:

- What action ran?
- What did the agent see before and after?
- Did the action actually succeed?
- If it failed, why?
- Can the failure be reproduced or replayed?

# Long-Term Architecture

```text
Computer-use agent or test runner
    ↓
Integration adapter
    ↓
Action recorder
    ↓
ActionRecord / ActionSession
    ↓
Artifacts
    ├── screenshots
    ├── JSON traces
    └── HTML timeline
    ↓
Verification
    ↓
Failure analysis
    ↓
Replay and evaluation
```

The agent decides what it wants to do.
Agent DevTools records, verifies, explains, and eventually replays what happened.

# Core Product Areas

1. Action observability
   Record action type, arguments, timing, status, errors, and artifacts.

2. Session tracing
   Group ordered actions into a complete execution timeline.

3. Verification
   Compare expected UI state with observed UI state after an action.

4. Failure analysis
   Classify failures such as:
   - wrong target;
   - blocked target;
   - timeout;
   - page not ready;
   - layout change;
   - operation error;
   - verification mismatch.

5. Replay
   Inspect or reproduce recorded actions in a controlled environment.

6. Integration
   Eventually support adapters for systems such as Playwright-based agents,
   browser-use, OpenClaw, and other computer-use runtimes.

# Current State

The repository currently includes:

- `ActionRecord` and `ActionStatus`;
- action execution recording;
- optional post-action verification orchestration in action and session recording;
- versioned JSON serialization and loading;
- atomic JSON persistence;
- `ActionSession`;
- persisted session goals, task-level verification, and final task outcomes;
- `SessionRecorder`, session resumption, and automatic task verification on
  successful context-manager exit;
- static HTML action and session reports with derived final outcomes;
- screenshot paths in action records and before-and-after capture through integration callbacks;
- Playwright verified-success, failure, and multi-action browser demonstrations;
- automated real-browser integration coverage for a successful click action;
- a minimal reusable contract for deterministic text-state verification;
- optional verification results persisted with action records;
- general action observations persisted separately from verification results;
- conservative structured failure categories for timeouts, operation errors,
  verification mismatches, and unknown failures;
- static session summaries with a prominent final result, action execution,
  failure, action-check coverage, and failure-category counts;
- controlled framework-independent replay for validated click actions, with
  real-browser success and timeout coverage and a controlled failure demo;
- a Playwright click adapter that records minimal element-state evidence and
  diagnoses missing, ambiguous, hidden, and disabled targets;
- Playwright fill failure diagnostics for missing, ambiguous, hidden, disabled,
  and non-editable targets;
- structured Playwright exact-text and element-visibility expectations with
  automatic waiting;
- automatic post-fill input-value observations and optional exact-value
  expectations;
- automatic before-and-after page URL observations for supported Playwright
  actions, displayed compactly in HTML reports;
- a Playwright action entry point for traced navigate, click, fill, press, and
  scroll
  trajectories;
- a single recorded Playwright executor that owns session and screenshot
  lifecycle for supported actions;
- a generic synchronous tool wrapper for recording public method calls with a
  single setup point;
- a generic sequential async tool wrapper that awaits tool execution and accepts
  synchronous or asynchronous screenshot, observation, and task-verification
  callbacks;
- optional automatic before-and-after structured state observations with
  deterministic changed paths and non-fatal observer errors;
- deterministic session analysis for repeated successful actions with unchanged
  structured state, shown as non-outcome-changing warnings in HTML reports;
- a Playwright tool wrapper that automatically captures screenshots and small
  page-state metadata without collecting page text, form values, or full DOM;
- bounded action-scoped Playwright `pageerror`, `console.error`, failed-request,
  and HTTP 4xx/5xx evidence for synchronous and asynchronous tools, with
  sanitized event URLs and prioritized likely-cause findings;
- composable synchronous and asynchronous Playwright task checks for URL
  components, element visibility, exact or contained text, and scalar DOM
  properties, with automatic verification and pytest-friendly assertions;
- synchronous and asynchronous observed-agent entry points that capture the
  user request as the goal, inject recorded Playwright tools, preserve the
  agent result, create unique run directories, and retain reports on errors;
- optional synchronous and asynchronous OpenAI and Gemini expectation generation that
  converts the captured request into bounded data-only Playwright task checks,
  preserves provider failures as unverified report metadata, and never blocks
  the agent run;
- a bounded Gemini function-calling adapter and local real-browser demo that
  records model-selected navigate, fill, and click actions without recording
  read-only observations as computer actions;
- optional final-state Gemini assessment that automatically compares the
  captured request with bounded final URL, title, heading, and rendered-text
  evidence after an observed agent returns;
- an optional Browser Use 0.13.x observer that wraps an existing agent once,
  records state-changing steps with screenshots, prevents unobserved initial
  actions, preserves existing callbacks, maps the framework judge into task
  verification, and reports bounded provider-startup failures;
- sequential repeated-run Browser Use stability evaluation with fresh Agent
  lifecycle ownership, numbered per-run traces, versioned aggregate JSON,
  deterministic trajectory divergence, conservative failure grouping, and a
  static aggregate HTML report;
- stable core and Playwright public import paths, plus a repeatable quickstart;
- wheel and source-distribution build validation with Python 3.11 through 3.14
  compatibility coverage;
- a bounded observe-decide-act Playwright loop with typed action decisions and
  automatic structured expectation verification;
- a deterministic local video-search agent trajectory demonstration;
- an optional live YouTube trajectory demonstration for manual testing;
- unit tests for the foundational modules.
- MIT-licensed packaging and automated GitHub Actions test coverage.

Action and task verification results are stored in JSON, displayed in HTML
reports, and included in derived action and session outcomes.
Replay does not support complete sessions or action types other than click.
Browser Use 0.13.x is the first official third-party agent integration. Other
agent frameworks still require dedicated adapters.
The observed-agent MVP requires an agent entry point shaped like
`run(user_request, *, tools=...)`; other framework call shapes need adapters.
Async tool recording intentionally rejects overlapping actions and uses
synchronous local writes for JSON and HTML persistence.
Action and session recorders can run caller-provided verification callbacks
before persistence. The model-agnostic core does not infer intent. The optional
OpenAI and Gemini Playwright integrations can propose conservative final-state
checks from the captured request; generated checks are hypotheses and may remain
unverified when context is insufficient.
Action-level Playwright expectations support exact text and input values, plus
single-element visibility. Task checks additionally support component URL
matching, contained text, and scalar DOM property equality.
Automatic trajectory analysis is intentionally limited to conservative
stuck-loop and explicit browser/runtime error warnings and does not infer
whether the user's task is correct.
Final-state AI assessment is optional and probabilistic. It is stored and
displayed separately from deterministic check semantics, may remain unverified,
and receives bounded visible page text that can still be sensitive.
Browser event evidence includes failed requests and HTTP 4xx/5xx responses but
does not include successful request timelines, request or response bodies,
headers, or cookies.

# Near-Term Roadmap

Follow this order unless the user explicitly changes direction:

Milestone 1:
Automated real-browser integration coverage. Complete for a successful click action.

Milestone 2:
A minimal verification contract. Complete for deterministic text-state comparisons:

- expected state;
- observed state;
- pass/fail result;
- evidence;
- failure reason.

Milestone 3:
Structured failure categories and failure summaries. Complete for categories
supported by explicit exception and verification signals.

Milestone 4:
A developer-friendly trace inspector or improved timeline. Complete for static
session overviews and failure-category counts.

Milestone 5:
Controlled replay of supported browser actions. Complete for synchronous click
actions with explicit selector and timeout validation.

Milestone 6:
One external agent integration adapter. Complete for Browser Use 0.13.x with
one-time wrapping, action screenshots, final-judge mapping, and real-browser
integration coverage.

Do not jump directly to dashboards, LLM integration, OpenClaw integration,
desktop automation, or complex replay before the foundations are tested.

# Engineering Principles

- Keep the core package model- and framework-agnostic.
- Prefer evidence over guesses.
- Treat screenshots, action metadata, and observed state as debugging evidence.
- Keep milestones small and independently demonstrable.
- Reuse existing public APIs before adding abstractions.
- Avoid premature abstraction and unrelated refactoring.
- Do not silently expand scope.
- Preserve backward compatibility for saved trace schemas where practical.
- Treat screenshots, typed text, action arguments, and exception messages as potentially sensitive.
- Keep dependencies minimal.
- Use deterministic local HTML pages for browser integration tests where possible.

# Task Workflow

For every implementation request:

1. Inspect the repository, relevant documentation, Git status, and existing tests.
2. State the smallest implementation plan before editing.
3. Implement only the requested milestone.
4. Add or update focused tests.
5. Run the relevant focused tests.
6. Run the full unit test suite.
7. Report:
   - files changed;
   - behavior added;
   - tests run and results;
   - limitations;
   - one recommended next milestone.
8. Do not commit or push unless explicitly requested.

# Definition of Done

A task is complete only when:

- behavior is implemented;
- relevant tests pass;
- existing tests still pass;
- generated artifacts use temporary or ignored directories;
- documentation is updated only when behavior exposed to users changes;
- no unrelated files are modified.

# Commit Convention

Use Semantic Commit Messages:

```text
<type>(<scope>): <subject>
```

Common types:

- feat
- fix
- test
- docs
- refactor
- chore

Keep commit subjects lowercase and concise.
