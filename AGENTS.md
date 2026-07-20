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
- versioned JSON serialization and loading;
- atomic JSON persistence;
- `ActionSession`;
- `SessionRecorder` and session resumption;
- static HTML action and session reports;
- screenshot paths in action records and before-and-after capture through integration callbacks;
- Playwright success, failure, and multi-action browser demonstrations;
- automated real-browser integration coverage for a successful click action;
- a minimal reusable contract for deterministic text-state verification;
- conservative structured failure categories for timeouts, operation errors,
  verification mismatches, and unknown failures;
- static session summaries with success, failure, and failure-category counts;
- controlled framework-independent replay for validated click actions, with
  real-browser success and timeout coverage and a controlled failure demo;
- unit tests for the foundational modules.

Verification results are not yet stored in trace JSON or HTML reports.
Replay does not support complete sessions or action types other than click.
General third-party agent integration is not implemented.

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
One external agent integration adapter.

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
