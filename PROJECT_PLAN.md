# Agent DevTools

## Goal

Provide action-level visual debugging and task verification for Browser Use
and Playwright agents.

## Problem

An agent tool call can return successfully while the user's task remains
unfinished. Developers need to see what each browser action did, what changed,
why an operation failed, and whether the complete trajectory reached its goal.

## Current Alpha

Agent DevTools can record supported browser actions into a versioned session
trace with:

- action arguments, timing, execution status, and bounded failure evidence;
- before-and-after screenshots and compact page-state observations;
- separate action checks and final task verification;
- JSON persistence and a static HTML timeline;
- Browser Use 0.13.x and lower-level Playwright integration paths.
- a framework-independent `observe_agent(...)` boundary for agents exposing
  `run(task, *, tools=...)`, with sync and async recording proxies.
- sequential repeated-run Browser Use evaluation with fresh Agents, preserved
  per-run traces, empirical pass-rate statistics, trajectory divergence, and a
  static aggregate stability report.
- optional deterministic Browser Use final-state checks for URL/title
  components, with the framework judge retained as supporting evidence.
- optional explicit TOML configuration for enabling recording, screenshots,
  metadata redaction, summaries, report opening, trace output, and
  repeated-evaluation output.
- a product-shaped repeated-run Browser Use example that keeps reports local,
  opens the aggregate report on request, and returns a CI-friendly non-zero
  status when not every run is explicitly passed.

The original one-action MVP is complete. Current work focuses on making this
browser-agent debugging workflow useful, understandable, and easy to adopt.

## Core Workflow

```text
Browser Use or Playwright agent
    → supported observer or wrapped tools
    → action and session records
    → screenshots, JSON, and HTML report
    → action checks and final task verification
    → optional repeated-run stability comparison
```

## Non-Goals for the Current Alpha

- Arbitrary desktop or Android interception
- Supporting every agent framework without an adapter
- Hosted dashboards or trace storage
- Model training
- General session replay or automatic recovery
- Concurrent evaluation, retries, or probabilistic reliability guarantees
- Recording hidden model reasoning

## Success Criteria

A developer can connect a supported browser agent, run its normal task, and
inspect a local report that clearly answers:

- Which actions executed?
- What changed after each action?
- Why did an action fail?
- Did the overall task actually succeed?
