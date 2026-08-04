# Development and testing

The repository uses a Python `src` layout and uv for dependency management.

## Core environment

```bash
uv sync
uv run pytest
```

Run a single test file while developing:

```bash
uv run pytest tests/test_action.py
```

## Playwright environment

```bash
uv sync --extra browser
uv run --extra browser playwright install chromium
uv run --extra browser pytest
```

On Ubuntu or WSL, install the required Chromium system packages when needed:

```bash
uv run --extra browser playwright install --with-deps chromium
```

## Browser Use environment

```bash
uv sync --extra browser-use
uv run --extra browser-use playwright install chromium
uv run --extra browser-use pytest \
  tests/test_browser_use_adapter.py \
  tests/test_public_api.py \
  tests/integration/test_browser_use_observer.py
```

Browser Use `0.13.7` pins older OpenAI and Google Gen AI SDKs. The
`browser-use` extra therefore conflicts with the separate `llm-openai` and
`llm-gemini` extras. CI tests these environments independently.

## Build the package

```bash
uv build
```

The build should produce a source distribution and wheel under `dist/`. Test a
wheel from a clean temporary project before publishing a release.

## Repository conventions

- Keep the core model and recorder independent of browser frameworks.
- Put framework-specific behavior under `src/agent_devtools/integrations/`.
- Keep optional dependencies behind extras.
- Add deterministic unit tests for behavior and integration tests for real
  framework boundaries.
- Do not commit generated `trace/` output or provider credentials.
- Keep failure classifications based on explicit evidence.

## Useful examples

```bash
uv run python examples/record_action.py
uv run --extra browser python examples/quickstart.py
uv run --extra browser python examples/browser_failure.py
uv run --extra browser-use python examples/browser_use_quickstart.py
uv run --extra browser-use python examples/browser_use_failure.py
```

Examples that call a model provider require the corresponding environment
variable. Local deterministic examples should remain the default choice for
tests and CI.
