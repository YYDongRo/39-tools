# Contributing to Agent DevTools

Thanks for helping make computer-use agents easier to observe and debug.

## Before starting

For a substantial feature or behavior change, open an issue first so the scope
and design can be discussed. Small bug fixes, documentation corrections, and
focused test improvements can go directly to a pull request.

Keep changes aligned with the current project scope: action recording,
verification, failure analysis, reports, replay, and agent integrations. Avoid
adding unrelated agent or model-framework behavior to the core package.

## Development setup

Agent DevTools requires Python 3.11 or newer and uses
[uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run pytest
```

Browser and Browser Use integrations have separate optional environments. See
[the development guide](docs/development.md) for their setup and test commands.

## Making a change

- Keep the core package model- and framework-agnostic.
- Add focused tests for changed behavior.
- Use deterministic local pages for browser tests when possible.
- Keep optional integrations behind dependency extras.
- Do not commit traces, screenshots containing private data, credentials, or
  provider keys.
- Update user documentation when a public API or workflow changes.

Before opening a pull request, run the smallest relevant tests and then the full
test suite for the environment you changed.

## Commits and pull requests

Use concise Semantic Commit Messages:

```text
<type>(<scope>): <subject>
```

In the pull request, explain the problem, the chosen behavior, tests run, and
any remaining limitations. Keep unrelated changes in separate pull requests.

