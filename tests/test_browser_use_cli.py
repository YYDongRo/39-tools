from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from agent_devtools.config import AgentDevToolsConfig


pytest.importorskip("browser_use")

MODULE_PATH = Path(__file__).parents[1] / "examples" / "browser_use_cli.py"
SPEC = importlib.util.spec_from_file_location("browser_use_cli_example", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_cli_accepts_explicit_config_path() -> None:
    args = MODULE._parser().parse_args(
        ["--config", "agent_devtools.windows.toml"]
    )

    assert args.config == Path("agent_devtools.windows.toml")


def test_cli_loads_explicit_config_path(tmp_path: Path) -> None:
    config_path = tmp_path / "windows.toml"
    config_path.write_text(
        "[agent_devtools]\nenabled = false\n",
        encoding="utf-8",
    )

    config = MODULE._load_config(config_path)

    assert config is not None
    assert config.enabled is False


def test_cli_reports_missing_explicit_config_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="does not exist"):
        MODULE._load_config(tmp_path / "missing.toml")


def test_browser_kwargs_use_managed_browser_by_default() -> None:
    assert MODULE._browser_kwargs(None, headed=True) == {"headless": False}


def test_browser_kwargs_use_configured_executable(tmp_path: Path) -> None:
    executable = tmp_path / "brave"
    executable.write_text("browser", encoding="utf-8")
    config = AgentDevToolsConfig(browser_executable_path=executable)

    assert MODULE._browser_kwargs(config, headed=False) == {
        "headless": True,
        "executable_path": str(executable),
    }


def test_browser_kwargs_reject_missing_executable() -> None:
    config = AgentDevToolsConfig(browser_executable_path=Path("missing-browser"))

    with pytest.raises(ValueError, match="browser executable was not found"):
        MODULE._browser_kwargs(config, headed=False)


def test_auto_provider_uses_only_configured_gemini_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENT_DEVTOOLS_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "gemini-test-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert MODULE._resolve_provider("auto") == "gemini"


def test_auto_provider_uses_only_configured_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENT_DEVTOOLS_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    assert MODULE._resolve_provider("auto") == "openai"


def test_auto_provider_requires_choice_when_multiple_keys_are_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENT_DEVTOOLS_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "gemini-test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    with pytest.raises(ValueError, match="multiple provider keys"):
        MODULE._resolve_provider("auto")


def test_explicit_provider_overrides_auto_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "gemini-test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    assert MODULE._resolve_provider("openai") == "openai"


def test_create_llm_builds_gemini_client_without_persisting_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "gemini-test-key")

    llm = MODULE._create_llm("gemini", None)

    assert type(llm).__name__ == "ChatGoogle"
    assert llm.model == "gemini-2.5-flash"


def test_create_llm_builds_openai_client_without_persisting_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")

    llm = MODULE._create_llm("openai", None)

    assert type(llm).__name__ == "ChatOpenAI"
    assert llm.model == "gpt-4o"
