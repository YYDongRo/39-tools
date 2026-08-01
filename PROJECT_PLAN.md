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

The original one-action MVP is complete. Current work focuses on making this
browser-agent debugging workflow useful, understandable, and easy to adopt.

## Core Workflow

```text
Browser Use or Playwright agent
    → supported observer or wrapped tools
    → action and session records
    → screenshots, JSON, and HTML report
    → action checks and final task verification
```

## Non-Goals for the Current Alpha

- Arbitrary desktop or Android interception
- Supporting every agent framework without an adapter
- Hosted dashboards or trace storage
- Model training
- General session replay or automatic recovery
- Recording hidden model reasoning

## Success Criteria

A developer can connect a supported browser agent, run its normal task, and
inspect a local report that clearly answers:

- Which actions executed?
- What changed after each action?
- Why did an action fail?
- Did the overall task actually succeed?
