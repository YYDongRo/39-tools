from math import nan
from pathlib import Path

import pytest

from agent_devtools import VerificationResult
from agent_devtools.integrations.playwright_task import (
    AllOf,
    all_of,
    element_visible,
    property_equals,
    text_contains,
    text_equals,
    url_matches,
    verify_playwright_task,
)
from agent_devtools.playwright import record_playwright_tools


class UrlPage:
    url = "https://www.youtube.com/watch?v=dynamic&list=ignored#player"


class EmptyTools:
    pass


def test_url_match_ignores_query_and_accepts_subdomains() -> None:
    result = verify_playwright_task(
        UrlPage(),
        url_matches(host="youtube.com", path_prefix="/watch"),
    )

    assert result.passed
    assert result.evidence["url"] == UrlPage.url


def test_all_of_reports_each_failed_url_check() -> None:
    result = verify_playwright_task(
        UrlPage(),
        all_of(
            url_matches(host="youtube.com"),
            url_matches(path_prefix="/shorts"),
        ),
    )

    assert not result.passed
    assert result.observed_state == "1 of 2 task checks passed"
    checks = result.evidence["checks"]
    assert isinstance(checks, list)
    assert [check["passed"] for check in checks] == [True, False]


def test_task_check_helpers_create_data_only_expectations() -> None:
    expectation = all_of(
        element_visible("video"),
        text_equals("h1", "Agent debugging"),
        text_contains("#status", "Playing"),
        property_equals("video", "paused", False),
    )

    assert isinstance(expectation, AllOf)
    assert len(expectation.checks) == 4


@pytest.mark.parametrize(
    "create_check",
    [
        lambda: url_matches(),
        lambda: url_matches(path_prefix="watch"),
        lambda: url_matches(host="https://youtube.com"),
        lambda: url_matches(scheme="not a scheme"),
        lambda: element_visible(""),
        lambda: text_contains("#status", "Ready", timeout_ms=0),
        lambda: text_contains("#status", ""),
        lambda: property_equals("video", "paused.value", False),
        lambda: property_equals("video", "duration", nan),
        lambda: all_of(),
    ],
)
def test_task_check_helpers_reject_invalid_rules(create_check: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        create_check()  # type: ignore[operator]


def test_playwright_recorder_rejects_invalid_task_expectation_early(
    tmp_path: Path,
) -> None:
    with pytest.raises(TypeError, match="task_expectation"):
        record_playwright_tools(
            EmptyTools(),
            UrlPage(),  # type: ignore[arg-type]
            tmp_path / "trace",
            goal="test a page",
            task_expectation="invalid",  # type: ignore[arg-type]
            capture_browser_events=False,
        )

    assert not (tmp_path / "trace").exists()


def test_playwright_recorder_rejects_two_task_verification_apis(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="either task_verification"):
        record_playwright_tools(
            EmptyTools(),
            UrlPage(),  # type: ignore[arg-type]
            tmp_path / "trace",
            goal="test a page",
            task_verification=lambda: VerificationResult(
                expected_state="done",
                observed_state="done",
                passed=True,
            ),
            task_expectation=url_matches(host="youtube.com"),
            capture_browser_events=False,
        )
