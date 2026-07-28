from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_devtools.integrations.playwright_task import (
    TaskExpectation,
    all_of,
    element_visible,
    property_equals,
    text_contains,
    text_equals,
    url_matches,
)


MAX_GENERATED_CHECKS = 5


@dataclass(frozen=True)
class GeneratedTaskExpectation:
    expectation: TaskExpectation | None
    inferred_goal: str | None
    source: str
    note: str | None = None

    def __post_init__(self) -> None:
        if self.inferred_goal is not None and (
            not isinstance(self.inferred_goal, str)
            or not self.inferred_goal.strip()
        ):
            raise ValueError("inferred_goal cannot be empty")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source cannot be empty")
        if self.note is not None and (
            not isinstance(self.note, str) or not self.note.strip()
        ):
            raise ValueError("note cannot be empty")


def task_expectation_from_plan(
    plan: object,
    *,
    source: str,
) -> GeneratedTaskExpectation:
    if not isinstance(plan, dict):
        raise ValueError("generated expectation plan must be an object")
    _require_fields(plan, {"inferred_goal", "can_verify", "reason", "checks"})

    inferred_goal = plan["inferred_goal"]
    can_verify = plan["can_verify"]
    reason = plan["reason"]
    checks = plan["checks"]
    if not isinstance(inferred_goal, str) or not inferred_goal.strip():
        raise ValueError("inferred_goal must be a non-empty string")
    if not isinstance(can_verify, bool):
        raise ValueError("can_verify must be a boolean")
    if reason is not None and (
        not isinstance(reason, str) or not reason.strip()
    ):
        raise ValueError("reason must be a non-empty string or null")
    if not isinstance(checks, list):
        raise ValueError("checks must be an array")
    if len(checks) > MAX_GENERATED_CHECKS:
        raise ValueError(f"checks cannot contain more than {MAX_GENERATED_CHECKS} items")

    if not can_verify:
        if checks:
            raise ValueError("an unverifiable plan cannot contain checks")
        if reason is None:
            raise ValueError("an unverifiable plan requires a reason")
        return GeneratedTaskExpectation(
            expectation=None,
            inferred_goal=inferred_goal,
            source=source,
            note=reason,
        )
    if not checks:
        raise ValueError("a verifiable plan requires at least one check")

    expectations = tuple(_check_from_dict(check) for check in checks)
    expectation = (
        expectations[0] if len(expectations) == 1 else all_of(*expectations)
    )
    return GeneratedTaskExpectation(
        expectation=expectation,
        inferred_goal=inferred_goal,
        source=source,
        note=reason,
    )


def task_expectation_response_format() -> dict[str, object]:
    nullable_string: dict[str, object] = {
        "anyOf": [{"type": "string"}, {"type": "null"}]
    }
    nullable_boolean: dict[str, object] = {
        "anyOf": [{"type": "boolean"}, {"type": "null"}]
    }
    nullable_integer: dict[str, object] = {
        "anyOf": [
            {"type": "integer", "minimum": 1},
            {"type": "null"},
        ]
    }
    return {
        "type": "json_schema",
        "name": "playwright_task_expectation",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["inferred_goal", "can_verify", "reason", "checks"],
            "properties": {
                "inferred_goal": {"type": "string"},
                "can_verify": {"type": "boolean"},
                "reason": nullable_string,
                "checks": {
                    "type": "array",
                    "maxItems": MAX_GENERATED_CHECKS,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "type",
                            "selector",
                            "expected_text",
                            "host",
                            "path_prefix",
                            "scheme",
                            "allow_subdomains",
                            "property_name",
                            "expected_value",
                            "timeout_ms",
                        ],
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "url_match",
                                    "element_visible",
                                    "text_equals",
                                    "text_contains",
                                    "property_equals",
                                ],
                            },
                            "selector": nullable_string,
                            "expected_text": nullable_string,
                            "host": nullable_string,
                            "path_prefix": nullable_string,
                            "scheme": nullable_string,
                            "allow_subdomains": nullable_boolean,
                            "property_name": nullable_string,
                            "expected_value": {
                                "anyOf": [
                                    {"type": "string"},
                                    {"type": "number"},
                                    {"type": "boolean"},
                                    {"type": "null"},
                                ]
                            },
                            "timeout_ms": nullable_integer,
                        },
                    },
                },
            },
        },
    }


def _check_from_dict(value: object) -> TaskExpectation:
    if not isinstance(value, dict):
        raise ValueError("each generated check must be an object")
    fields = {
        "type",
        "selector",
        "expected_text",
        "host",
        "path_prefix",
        "scheme",
        "allow_subdomains",
        "property_name",
        "expected_value",
        "timeout_ms",
    }
    _require_fields(value, fields)
    check_type = value["type"]
    timeout_ms = value["timeout_ms"]
    if timeout_ms is None:
        timeout_ms = 2_000
    if (
        not isinstance(timeout_ms, int)
        or isinstance(timeout_ms, bool)
        or timeout_ms <= 0
    ):
        raise ValueError("timeout_ms must be a positive integer or null")

    if check_type == "url_match":
        allow_subdomains = value["allow_subdomains"]
        if not isinstance(allow_subdomains, bool):
            raise ValueError("url_match requires allow_subdomains")
        return url_matches(
            host=_optional_string(value["host"], "host"),
            path_prefix=_optional_string(value["path_prefix"], "path_prefix"),
            scheme=_optional_string(value["scheme"], "scheme"),
            allow_subdomains=allow_subdomains,
        )

    selector = _required_string(value["selector"], "selector")
    if check_type == "element_visible":
        return element_visible(selector, timeout_ms=timeout_ms)
    if check_type in {"text_equals", "text_contains"}:
        expected_text = _required_string(value["expected_text"], "expected_text")
        helper = text_equals if check_type == "text_equals" else text_contains
        return helper(selector, expected_text, timeout_ms=timeout_ms)
    if check_type == "property_equals":
        property_name = _required_string(value["property_name"], "property_name")
        expected_value: Any = value["expected_value"]
        return property_equals(
            selector,
            property_name,
            expected_value,
            timeout_ms=timeout_ms,
        )
    raise ValueError(f"unsupported generated check type: {check_type!r}")


def _require_fields(value: dict[object, object], expected: set[str]) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected.difference(actual))
        extra = sorted(actual.difference(expected), key=repr)
        raise ValueError(f"invalid generated fields; missing={missing}, extra={extra}")


def _required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, field_name)


__all__ = [
    "GeneratedTaskExpectation",
    "MAX_GENERATED_CHECKS",
    "task_expectation_from_plan",
    "task_expectation_response_format",
]
