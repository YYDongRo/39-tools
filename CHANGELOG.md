# Changelog

All notable changes to Agent DevTools are recorded here.

## Unreleased

- Add the installable `agent-devtools` command for the Browser Use workflow.
- Add an optional versioned `--summary-json` output for CI result checks.
- Add a tolerant hostname check for successful Browser Use `navigate` actions.
- Add optional same-task evaluation comparisons with concise JSON and HTML
  regression reports.
- Add `--runs N` to the installed Browser Use CLI for fresh-agent stability
  evaluations and aggregate reports.
- Keep the installed Browser Use CLI's final result summary concise and
  avoid duplicate report and task-result lines.
- Allow generic sync and async observers to bind their recording proxy to an
  agent's existing tool attribute for one-time dispatcher integration.
- Keep `examples/browser_use_cli.py` as a compatibility wrapper.
- Document the current Python, Browser Use, and Playwright support baseline.

The project is still an alpha and has not been published to PyPI.
