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
- Check `uv lock --check` and `git diff --check`.
- Review generated traces and screenshots for secrets or private data.

## Publication

- Confirm the release notes and supported-version matrix are accurate.
- Review the wheel contents and package metadata.
- Tag the release only after the CI workflow is green.
- Publish only after a maintainer explicitly approves the distribution target.
