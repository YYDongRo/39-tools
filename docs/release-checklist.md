# Release checklist

Use this checklist before publishing an Agent DevTools release.

## Package and compatibility

- Update the version in `pyproject.toml` and `uv.lock`.
- Update `CHANGELOG.md` with user-visible changes and limitations.
- Verify Python 3.11–3.14 and the documented Browser Use/Playwright ranges.
- Build both the wheel and source distribution with `uv build`.
- Install the wheel in a clean environment and run `agent-devtools --help`.

## Behavior and evidence

- Run the core, browser, and Browser Use test groups.
- Run the deterministic sample and inspect its HTML report.
- Run one real local Browser Use task when provider credentials are available.
- Exercise both local control-center paths: **Run Browser Use task** and
  **Connect your agent**. Confirm the latter keeps task input in the existing
  agent CLI or application and records only calls through the documented tool
  boundary.
- Run `uv run python examples/generic_agent.py` once with its default failing
  final check and once with `--correct`; inspect both reports and confirm that
  the documentation does not imply a bundled desktop agent.
- Check `uv lock --check` and `git diff --check`.
- Review generated traces and screenshots for secrets or private data.

## User-facing setup

- Confirm README and the CLI guide use the release tag, supported version
  ranges, and the same `39-tools` / `agent_devtools` / `agent-devtools` naming.
- Confirm provider keys are documented as environment variables and are not
  accepted or persisted by the local dashboard.
- Confirm the scope warning says that direct unwrapped browser, desktop, and
  Android calls are outside the recording boundary.

## Publication

- Confirm the release notes and supported-version matrix are accurate.
- Review the wheel contents and package metadata.
- Tag the release only after the CI workflow is green.
- Publish only after a maintainer explicitly approves the distribution target.
