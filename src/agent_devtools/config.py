from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentDevToolsConfig:
    """Small, optional configuration for Browser Use recording and evaluation."""

    enabled: bool = True
    screenshots: bool = True
    redact_sensitive_data: bool = True
    terminal_summary: bool = True
    open_report: bool = False
    trace_directory: Path = Path("trace") / "browser-use"
    evaluation_directory: Path = Path("evaluations") / "browser-use"

    @classmethod
    def from_file(cls, path: str | Path) -> "AgentDevToolsConfig":
        config_path = Path(path)
        try:
            raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"Agent DevTools config does not exist: {config_path}"
            ) from error
        except tomllib.TOMLDecodeError as error:
            raise ValueError(
                f"invalid Agent DevTools TOML config: {config_path}"
            ) from error
        return cls.from_mapping(raw, source=config_path)

    @classmethod
    def from_mapping(
        cls,
        raw: object,
        *,
        source: str | Path = "config",
    ) -> "AgentDevToolsConfig":
        if not isinstance(raw, dict):
            raise TypeError(f"Agent DevTools config must be a TOML table: {source}")

        section = raw.get("agent_devtools", raw)
        if not isinstance(section, dict):
            raise TypeError(
                f"[agent_devtools] must be a TOML table: {source}"
            )

        allowed = {
            "enabled",
            "screenshots",
            "redact_sensitive_data",
            "terminal_summary",
            "open_report",
            "trace_directory",
            "evaluation_directory",
        }
        unknown = set(section).difference(allowed)
        if unknown:
            names = ", ".join(sorted(str(name) for name in unknown))
            raise ValueError(f"unknown Agent DevTools config option(s): {names}")

        values = {
            "enabled": _bool_option(section, "enabled", True),
            "screenshots": _bool_option(section, "screenshots", True),
            "redact_sensitive_data": _bool_option(
                section,
                "redact_sensitive_data",
                True,
            ),
            "terminal_summary": _bool_option(
                section,
                "terminal_summary",
                True,
            ),
            "open_report": _bool_option(section, "open_report", False),
            "trace_directory": _path_option(
                section,
                "trace_directory",
                Path("trace") / "browser-use",
            ),
            "evaluation_directory": _path_option(
                section,
                "evaluation_directory",
                Path("evaluations") / "browser-use",
            ),
        }
        return cls(**values)


def _bool_option(section: dict[object, object], name: str, default: bool) -> bool:
    value = section.get(name, default)
    if not isinstance(value, bool):
        raise TypeError(f"Agent DevTools config option {name!r} must be a boolean")
    return value


def _path_option(
    section: dict[object, object],
    name: str,
    default: Path,
) -> Path:
    value = section.get(name, default.as_posix())
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"Agent DevTools config option {name!r} must be a path")
    return Path(value)


__all__ = ["AgentDevToolsConfig"]
