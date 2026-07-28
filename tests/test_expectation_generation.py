import pytest

from agent_devtools.integrations.playwright_expectation_generation import (
    GeneratedTaskExpectation,
    task_expectation_from_plan,
    task_expectation_response_format,
)
from agent_devtools.integrations.playwright_task import (
    AllOf,
    PropertyEquals,
    UrlMatch,
)


def _check(check_type: str, **updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "type": check_type,
        "selector": None,
        "expected_text": None,
        "host": None,
        "path_prefix": None,
        "scheme": None,
        "allow_subdomains": None,
        "property_name": None,
        "expected_value": None,
        "timeout_ms": None,
    }
    value.update(updates)
    return value


def test_convert_generated_plan_to_bounded_task_checks() -> None:
    generated = task_expectation_from_plan(
        {
            "inferred_goal": "Open a YouTube watch page and play its video",
            "can_verify": True,
            "reason": "Check destination and playback state.",
            "checks": [
                _check(
                    "url_match",
                    host="youtube.com",
                    path_prefix="/watch",
                    allow_subdomains=True,
                ),
                _check(
                    "property_equals",
                    selector="video",
                    property_name="paused",
                    expected_value=False,
                ),
            ],
        },
        source="openai:test-model",
    )

    assert isinstance(generated, GeneratedTaskExpectation)
    assert generated.inferred_goal == "Open a YouTube watch page and play its video"
    assert generated.source == "openai:test-model"
    assert isinstance(generated.expectation, AllOf)
    assert isinstance(generated.expectation.checks[0], UrlMatch)
    assert isinstance(generated.expectation.checks[1], PropertyEquals)
    assert generated.expectation.checks[1].expected is False


def test_unverifiable_plan_has_a_clear_note_and_no_check() -> None:
    generated = task_expectation_from_plan(
        {
            "inferred_goal": "Complete an unspecified browser task",
            "can_verify": False,
            "reason": "No observable final state was supplied.",
            "checks": [],
        },
        source="openai:test-model",
    )

    assert generated.expectation is None
    assert generated.note == "No observable final state was supplied."


def test_reject_more_than_five_generated_checks() -> None:
    plan = {
        "inferred_goal": "Show the page",
        "can_verify": True,
        "reason": None,
        "checks": [
            _check("element_visible", selector="main") for _ in range(6)
        ],
    }

    with pytest.raises(ValueError, match="more than 5"):
        task_expectation_from_plan(plan, source="test")


def test_reject_generated_plan_with_extra_fields() -> None:
    plan = {
        "inferred_goal": "Show the page",
        "can_verify": False,
        "reason": "Not enough context.",
        "checks": [],
        "javascript": "return true",
    }

    with pytest.raises(ValueError, match="invalid generated fields"):
        task_expectation_from_plan(plan, source="test")


def test_response_format_is_strict_and_disallows_extra_fields() -> None:
    response_format = task_expectation_response_format()
    schema = response_format["schema"]

    assert response_format["strict"] is True
    assert isinstance(schema, dict)
    assert schema["additionalProperties"] is False
    checks = schema["properties"]["checks"]  # type: ignore[index]
    assert checks["maxItems"] == 5
    assert checks["items"]["additionalProperties"] is False
