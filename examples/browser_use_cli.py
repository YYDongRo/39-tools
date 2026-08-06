"""Compatibility wrapper for the installed ``agent-devtools`` command."""

from __future__ import annotations

import asyncio

from agent_devtools.cli import (
    _browser_use_main as main,
    _browser_use_parser as _parser,
    _browser_kwargs,
    _create_llm,
    _load_config,
    _resolve_provider,
)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
