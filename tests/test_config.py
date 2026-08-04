from pathlib import Path

import pytest

from agent_devtools.config import AgentDevToolsConfig


def test_config_defaults_preserve_observer_behavior() -> None:
    config = AgentDevToolsConfig()

    assert config.enabled is True
    assert config.screenshots is True
    assert config.terminal_summary is True
    assert config.open_report is False
    assert config.trace_directory == Path("trace") / "browser-use"


def test_config_reads_human_editable_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "agent_devtools.toml"
    config_path.write_text(
        """\
[agent_devtools]
enabled = false
screenshots = false
terminal_summary = false
open_report = true
trace_directory = "custom-trace"
""",
        encoding="utf-8",
    )

    config = AgentDevToolsConfig.from_file(config_path)

    assert config == AgentDevToolsConfig(
        enabled=False,
        screenshots=False,
        terminal_summary=False,
        open_report=True,
        trace_directory=Path("custom-trace"),
    )


def test_config_rejects_unknown_options() -> None:
    with pytest.raises(ValueError, match="unknown Agent DevTools config"):
        AgentDevToolsConfig.from_mapping(
            {"agent_devtools": {"not_a_real_option": True}}
        )


def test_config_rejects_wrong_option_types() -> None:
    with pytest.raises(TypeError, match="must be a boolean"):
        AgentDevToolsConfig.from_mapping(
            {"agent_devtools": {"screenshots": "yes"}}
        )

    with pytest.raises(TypeError, match="must be a path"):
        AgentDevToolsConfig.from_mapping(
            {"agent_devtools": {"trace_directory": "   "}}
        )


def test_config_reports_missing_and_invalid_files(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="does not exist"):
        AgentDevToolsConfig.from_file(tmp_path / "missing.toml")

    invalid = tmp_path / "invalid.toml"
    invalid.write_text("[agent_devtools", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid Agent DevTools TOML"):
        AgentDevToolsConfig.from_file(invalid)
