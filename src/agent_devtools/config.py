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
    compare_previous: bool = False
    trace_directory: Path = Path("trace") / "browser-use"
    evaluation_directory: Path = Path("evaluations") / "browser-use"
    browser_executable_path: Path | None = None

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
            "compare_previous",
            "trace_directory",
            "evaluation_directory",
            "browser",
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
            "compare_previous": _bool_option(
                section,
                "compare_previous",
                False,
            ),
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
            "browser_executable_path": _browser_executable_path(section),
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


def _browser_executable_path(
    section: dict[object, object],
) -> Path | None:
    value = section.get("browser", {})
    if not isinstance(value, dict):
        raise TypeError(
            "Agent DevTools config section 'browser' must be a TOML table"
        )

    unknown = set(value).difference({"executable_path"})
    if unknown:
        names = ", ".join(sorted(str(name) for name in unknown))
        raise ValueError(
            "unknown Agent DevTools browser option(s): " + names
        )

    executable_path = value.get("executable_path")
    if executable_path is None:
        return None
    if not isinstance(executable_path, str) or not executable_path.strip():
        raise TypeError(
            "Agent DevTools config option 'browser.executable_path' "
            "must be a path"
        )
    return Path(executable_path)


__all__ = ["AgentDevToolsConfig"]
