from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from agent_devtools.runtime import RuntimeContext, collect_runtime_context
from agent_devtools.serialization import read_session_json, write_session_json
from agent_devtools.session import ActionSession


def _context() -> RuntimeContext:
    return RuntimeContext(
        agent_devtools_version="0.1.0",
        python_version="3.14.2",
        os_name="Linux",
        os_version="6.6",
        architecture="x86_64",
        playwright_version="1.61.0",
        browser_use_version=None,
    )


def test_runtime_context_is_immutable_and_validated() -> None:
    context = _context()

    with pytest.raises(FrozenInstanceError):
        context.python_version = "3.15"  # type: ignore[misc]

    with pytest.raises(ValueError, match="os_name cannot be empty"):
        RuntimeContext(
            agent_devtools_version="0.1.0",
            python_version="3.14.2",
            os_name=" ",
            os_version="6.6",
            architecture="x86_64",
        )


def test_collect_runtime_context_uses_safe_allowlisted_values() -> None:
    context = collect_runtime_context()

    assert context.agent_devtools_version
    assert context.python_version
    assert context.os_name
    assert context.os_version
    assert context.architecture
    values = vars(context).values()
    assert all(isinstance(value, (str, type(None))) for value in values)
    assert all("API_KEY" not in str(value) for value in values)
    assert all("file://" not in str(value) for value in values)


def test_session_runtime_context_json_round_trip(tmp_path: Path) -> None:
    session = ActionSession(goal="Open the page", run_context=_context())
    output_path = tmp_path / "session.json"

    write_session_json(session, output_path)

    loaded = read_session_json(output_path)
    assert loaded == session
    assert loaded.run_context == _context()


def test_old_session_without_runtime_context_still_loads() -> None:
    session = ActionSession(goal="Open the page")
    data = {
        "schema_version": 3,
        "goal": session.goal,
        "inferred_goal": None,
        "verification_source": None,
        "verification_note": None,
        "verification": None,
        "actions": [],
    }

    from agent_devtools.serialization import session_from_dict

    loaded = session_from_dict(data)
    assert loaded.run_context is None
