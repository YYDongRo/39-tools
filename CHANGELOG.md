# Changelog

All notable changes to Agent DevTools are recorded here.

## Unreleased

## 0.2.0a1 - 2026-08-11

- Add a local control center with focused entry points for running Browser Use
  tasks, connecting a compatible custom agent, checking setup health, and
  opening all local reports.
- Add a one-time custom-agent connection guide that keeps task input in the
  developer's existing CLI or application and explains the recording boundary.
- Keep the latest run and recent reports compact so the control center is useful
  during a task without replacing the agent or uploading trace data.
- Clarify provider-key setup, local-only report handling, and the difference
  between the `39-tools` distribution, `agent_devtools` import, and
  `agent-devtools` command.
- Keep this release alpha: direct unwrapped desktop or native calls are not
  automatically captured, and the package is not published on PyPI.

## 0.1.0 - 2026-08-08

- Add the installable `agent-devtools` command for the Browser Use workflow.
- Add an optional versioned `--summary-json` output for CI result checks.
- Add a tolerant hostname check for successful Browser Use `navigate` actions.
- Add optional same-task evaluation comparisons with concise JSON and HTML
  regression reports.
- Add `--runs N` to the installed Browser Use CLI for fresh-agent stability
  evaluations and aggregate reports.
- Keep the installed Browser Use CLI's final result summary concise and
  avoid duplicate report and task-result lines.
- Put before/after visual evidence ahead of collapsed technical details in
  session reports for faster failure triage.
- Warn clearly when a run contains no captured browser actions, including the
  boundary where direct calls may be outside observation.
- Add an optional strict recording-coverage gate for zero-action runs.
- Add a Browser Use preflight check for the recording hook and trace setup.
- Allow generic sync and async observers to bind their recording proxy to an
  agent's existing tool attribute for one-time dispatcher integration.
- Keep `examples/browser_use_cli.py` as a compatibility wrapper.
- Document the current Python, Browser Use, and Playwright support baseline.

This release is alpha and has not been published to PyPI.
