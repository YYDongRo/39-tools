from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


pytest.importorskip("browser_use")

MODULE_PATH = (
    Path(__file__).parents[1] / "examples" / "browser_use_evaluation.py"
)
SPEC = importlib.util.spec_from_file_location(
    "browser_use_evaluation_example", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_evaluation_cli_accepts_domains_and_final_state_filters() -> None:
    args = MODULE._parser().parse_args(
        [
            "--allowed-domain",
            "youtube.com",
            "--allowed-domain",
            "googlevideo.com",
            "--url-contains",
            "youtube.com/watch",
            "--title-contains",
            "Miku",
        ]
    )

    assert args.allowed_domains == ["youtube.com", "googlevideo.com"]
    assert args.url_contains == "youtube.com/watch"
    assert args.title_contains == "Miku"


def test_evaluation_browser_kwargs_default_to_example_domain() -> None:
    assert MODULE._browser_kwargs(None, headed=True) == {
        "headless": False,
        "allowed_domains": ["example.com"],
    }


def test_evaluation_browser_kwargs_use_requested_domains() -> None:
    assert MODULE._browser_kwargs(
        None,
        headed=False,
        allowed_domains=[" youtube.com ", "googlevideo.com"],
    ) == {
        "headless": True,
        "allowed_domains": ["youtube.com", "googlevideo.com"],
    }


def test_evaluation_rejects_empty_allowed_domain() -> None:
    with pytest.raises(ValueError, match="allowed domains cannot be empty"):
        MODULE._browser_kwargs(None, headed=False, allowed_domains=[""])


def test_evaluation_final_check_is_optional_or_combined() -> None:
    assert MODULE._final_check(url_contains=None, title_contains=None) is None

    check = MODULE._final_check(
        url_contains="youtube.com/watch",
        title_contains="Miku",
    )
    assert check is not None
    result = check(
        {
            "url": "https://www.youtube.com/watch?v=123",
            "title": "Hatsune Miku Expo",
        }
    )
    assert result.passed is True
