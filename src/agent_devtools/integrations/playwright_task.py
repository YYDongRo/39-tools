from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from re import fullmatch
from urllib.parse import urlsplit

from agent_devtools.verification import VerificationResult


JsonScalar = str | int | float | bool | None


@dataclass(frozen=True)
class UrlMatch:
    host: str | None = None
    path_prefix: str | None = None
    scheme: str | None = None
    allow_subdomains: bool = True

    def __post_init__(self) -> None:
        if self.host is not None and (
            not isinstance(self.host, str) or not self.host.strip()
        ):
            raise ValueError("host cannot be empty")
        if self.host is not None and (
            self.host != self.host.strip()
            or any(character in self.host for character in ":/?#")
            or any(character.isspace() for character in self.host)
        ):
            raise ValueError("host must contain only a hostname")
        if self.path_prefix is not None and (
            not isinstance(self.path_prefix, str)
            or not self.path_prefix.startswith("/")
        ):
            raise ValueError("path_prefix must start with '/'")
        if self.scheme is not None and (
            not isinstance(self.scheme, str)
            or fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*", self.scheme) is None
        ):
            raise ValueError("scheme must be a valid URL scheme")
        if not isinstance(self.allow_subdomains, bool):
            raise TypeError("allow_subdomains must be a boolean")
        if self.host is None and self.path_prefix is None and self.scheme is None:
            raise ValueError("URL matching requires at least one condition")


@dataclass(frozen=True)
class ElementVisible:
    selector: str
    timeout_ms: int = 2_000

    def __post_init__(self) -> None:
        _validate_selector(self.selector)
        _validate_timeout(self.timeout_ms)


@dataclass(frozen=True)
class TextMatch:
    selector: str
    expected: str
    contains: bool = False
    timeout_ms: int = 2_000

    def __post_init__(self) -> None:
        _validate_selector(self.selector)
        if not isinstance(self.expected, str):
            raise TypeError("expected text must be a string")
        if not isinstance(self.contains, bool):
            raise TypeError("contains must be a boolean")
        if self.contains and not self.expected:
            raise ValueError("contained text cannot be empty")
        _validate_timeout(self.timeout_ms)


@dataclass(frozen=True)
class PropertyEquals:
    selector: str
    property_name: str
    expected: JsonScalar
    timeout_ms: int = 2_000

    def __post_init__(self) -> None:
        _validate_selector(self.selector)
        if (
            not isinstance(self.property_name, str)
            or not self.property_name.isidentifier()
        ):
            raise ValueError("property_name must be a simple identifier")
        if not _is_json_scalar(self.expected):
            raise TypeError("expected property value must be a JSON scalar")
        _validate_timeout(self.timeout_ms)


@dataclass(frozen=True)
class AllOf:
    checks: tuple[TaskExpectation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.checks, tuple):
            raise TypeError("checks must be a tuple")
        if not self.checks:
            raise ValueError("all_of requires at least one check")
        for check in self.checks:
            validate_task_expectation(check)


TaskExpectation = UrlMatch | ElementVisible | TextMatch | PropertyEquals | AllOf


def url_matches(
    *,
    host: str | None = None,
    path_prefix: str | None = None,
    scheme: str | None = None,
    allow_subdomains: bool = True,
) -> UrlMatch:
    return UrlMatch(
        host=host,
        path_prefix=path_prefix,
        scheme=scheme,
        allow_subdomains=allow_subdomains,
    )


def element_visible(selector: str, *, timeout_ms: int = 2_000) -> ElementVisible:
    return ElementVisible(selector, timeout_ms)


def text_equals(
    selector: str,
    expected: str,
    *,
    timeout_ms: int = 2_000,
) -> TextMatch:
    return TextMatch(selector, expected, timeout_ms=timeout_ms)


def text_contains(
    selector: str,
    expected: str,
    *,
    timeout_ms: int = 2_000,
) -> TextMatch:
    return TextMatch(selector, expected, contains=True, timeout_ms=timeout_ms)


def property_equals(
    selector: str,
    property_name: str,
    expected: JsonScalar,
    *,
    timeout_ms: int = 2_000,
) -> PropertyEquals:
    return PropertyEquals(selector, property_name, expected, timeout_ms)


def all_of(*checks: TaskExpectation) -> AllOf:
    return AllOf(tuple(checks))


def verify_playwright_task(
    page: object,
    expectation: TaskExpectation,
) -> VerificationResult:
    validate_task_expectation(expectation)
    if isinstance(expectation, AllOf):
        return _combine_results(
            [verify_playwright_task(page, check) for check in expectation.checks]
        )
    if isinstance(expectation, UrlMatch):
        return _verify_url(str(getattr(page, "url")), expectation)
    if isinstance(expectation, ElementVisible):
        return _verify_visible(page, expectation)
    if isinstance(expectation, TextMatch):
        return _verify_text(page, expectation)
    return _verify_property(page, expectation)


async def verify_async_playwright_task(
    page: object,
    expectation: TaskExpectation,
) -> VerificationResult:
    validate_task_expectation(expectation)
    if isinstance(expectation, AllOf):
        results = []
        for check in expectation.checks:
            results.append(await verify_async_playwright_task(page, check))
        return _combine_results(results)
    if isinstance(expectation, UrlMatch):
        return _verify_url(str(getattr(page, "url")), expectation)
    if isinstance(expectation, ElementVisible):
        return await _verify_visible_async(page, expectation)
    if isinstance(expectation, TextMatch):
        return await _verify_text_async(page, expectation)
    return await _verify_property_async(page, expectation)


def _verify_url(observed_url: str, check: UrlMatch) -> VerificationResult:
    parsed = urlsplit(observed_url)
    observed_host = (parsed.hostname or "").lower()
    expected_host = check.host.lower() if check.host is not None else None
    host_matches = expected_host is None or observed_host == expected_host
    if expected_host is not None and check.allow_subdomains:
        host_matches = host_matches or observed_host.endswith(f".{expected_host}")
    path_matches = (
        check.path_prefix is None or parsed.path.startswith(check.path_prefix)
    )
    scheme_matches = check.scheme is None or parsed.scheme == check.scheme.lower()
    passed = host_matches and path_matches and scheme_matches
    expected_state = _url_description(check)
    evidence: dict[str, object] = {
        "expectation_type": "url_match",
        "host": check.host,
        "path_prefix": check.path_prefix,
        "scheme": check.scheme,
        "allow_subdomains": check.allow_subdomains,
        "url": observed_url,
    }
    return VerificationResult(
        expected_state=expected_state,
        observed_state=f"URL is {observed_url!r}",
        passed=passed,
        evidence=evidence,
        failure_reason=None if passed else f"expected {expected_state}",
    )


def _verify_visible(page: object, check: ElementVisible) -> VerificationResult:
    from playwright.sync_api import expect

    locator = page.locator(check.selector)  # type: ignore[attr-defined]
    try:
        expect(locator).to_have_count(1, timeout=check.timeout_ms)
        expect(locator).to_be_visible(timeout=check.timeout_ms)
    except AssertionError:
        count = _safe_sync(locator.count, 0)
        visible = _safe_sync(locator.first.is_visible, None) if count else None
    except Exception as error:
        return _evaluation_failure("element visibility", check.selector, error)
    else:
        count = 1
        visible = True

    expected = f"{check.selector!r} is visible"
    passed = count == 1 and visible is True
    observed = (
        expected
        if passed
        else f"{count} matching elements; visible={visible!r}"
    )
    return _check_result(
        expected,
        observed,
        passed,
        {
            "expectation_type": "element_visible",
            "selector": check.selector,
            "selector_count": count,
            "target_visible": visible,
            "timeout_ms": check.timeout_ms,
        },
    )


async def _verify_visible_async(
    page: object,
    check: ElementVisible,
) -> VerificationResult:
    from playwright.async_api import expect

    locator = page.locator(check.selector)  # type: ignore[attr-defined]
    try:
        await expect(locator).to_have_count(1, timeout=check.timeout_ms)
        await expect(locator).to_be_visible(timeout=check.timeout_ms)
    except AssertionError:
        count = await _safe_async(locator.count, 0)
        visible = await _safe_async(locator.first.is_visible, None) if count else None
    except Exception as error:
        return _evaluation_failure("element visibility", check.selector, error)
    else:
        count = 1
        visible = True

    expected = f"{check.selector!r} is visible"
    passed = count == 1 and visible is True
    observed = expected if passed else f"{count} matching elements; visible={visible!r}"
    return _check_result(
        expected,
        observed,
        passed,
        {
            "expectation_type": "element_visible",
            "selector": check.selector,
            "selector_count": count,
            "target_visible": visible,
            "timeout_ms": check.timeout_ms,
        },
    )


def _verify_text(page: object, check: TextMatch) -> VerificationResult:
    from playwright.sync_api import expect

    locator = page.locator(check.selector)  # type: ignore[attr-defined]
    try:
        expect(locator).to_have_count(1, timeout=check.timeout_ms)
        if check.contains:
            expect(locator).to_contain_text(check.expected, timeout=check.timeout_ms)
        else:
            expect(locator).to_have_text(
                check.expected,
                timeout=check.timeout_ms,
                use_inner_text=True,
            )
    except AssertionError:
        count = _safe_sync(locator.count, 0)
        observed = (
            _safe_sync(locator.first.inner_text, "<unavailable>")
            if count
            else "<element not found>"
        )
    except Exception as error:
        return _evaluation_failure("element text", check.selector, error)
    else:
        count = 1
        observed = locator.inner_text()

    relation = "contains" if check.contains else "equals"
    expected = f"text of {check.selector!r} {relation} {check.expected!r}"
    passed = count == 1 and (
        check.expected in observed if check.contains else observed == check.expected
    )
    return _check_result(
        expected,
        f"text is {observed!r}",
        passed,
        {
            "expectation_type": f"text_{relation}",
            "selector": check.selector,
            "selector_count": count,
            "text": observed,
            "timeout_ms": check.timeout_ms,
        },
    )


async def _verify_text_async(
    page: object,
    check: TextMatch,
) -> VerificationResult:
    from playwright.async_api import expect

    locator = page.locator(check.selector)  # type: ignore[attr-defined]
    try:
        await expect(locator).to_have_count(1, timeout=check.timeout_ms)
        if check.contains:
            await expect(locator).to_contain_text(
                check.expected,
                timeout=check.timeout_ms,
            )
        else:
            await expect(locator).to_have_text(
                check.expected,
                timeout=check.timeout_ms,
                use_inner_text=True,
            )
    except AssertionError:
        count = await _safe_async(locator.count, 0)
        observed = (
            await _safe_async(locator.first.inner_text, "<unavailable>")
            if count
            else "<element not found>"
        )
    except Exception as error:
        return _evaluation_failure("element text", check.selector, error)
    else:
        count = 1
        observed = await locator.inner_text()

    relation = "contains" if check.contains else "equals"
    expected = f"text of {check.selector!r} {relation} {check.expected!r}"
    passed = count == 1 and (
        check.expected in observed if check.contains else observed == check.expected
    )
    return _check_result(
        expected,
        f"text is {observed!r}",
        passed,
        {
            "expectation_type": f"text_{relation}",
            "selector": check.selector,
            "selector_count": count,
            "text": observed,
            "timeout_ms": check.timeout_ms,
        },
    )


def _verify_property(page: object, check: PropertyEquals) -> VerificationResult:
    from playwright.sync_api import expect

    locator = page.locator(check.selector)  # type: ignore[attr-defined]
    try:
        expect(locator).to_have_count(1, timeout=check.timeout_ms)
        expect(locator).to_have_js_property(
            check.property_name,
            check.expected,
            timeout=check.timeout_ms,
        )
    except AssertionError:
        count = _safe_sync(locator.count, 0)
        observed = (
            _safe_sync(
                lambda: locator.first.evaluate(
                    "(element, name) => element[name]",
                    check.property_name,
                ),
                "<unavailable>",
            )
            if count
            else "<element not found>"
        )
    except Exception as error:
        return _evaluation_failure("element property", check.selector, error)
    else:
        count = 1
        observed = locator.evaluate(
            "(element, name) => element[name]",
            check.property_name,
        )

    expected = (
        f"property {check.property_name!r} of {check.selector!r} "
        f"equals {check.expected!r}"
    )
    passed = count == 1 and observed == check.expected
    return _check_result(
        expected,
        f"property value is {observed!r}",
        passed,
        {
            "expectation_type": "property_equals",
            "selector": check.selector,
            "selector_count": count,
            "property_name": check.property_name,
            "expected": check.expected,
            "observed": observed,
            "timeout_ms": check.timeout_ms,
        },
    )


async def _verify_property_async(
    page: object,
    check: PropertyEquals,
) -> VerificationResult:
    from playwright.async_api import expect

    locator = page.locator(check.selector)  # type: ignore[attr-defined]
    try:
        await expect(locator).to_have_count(1, timeout=check.timeout_ms)
        await expect(locator).to_have_js_property(
            check.property_name,
            check.expected,
            timeout=check.timeout_ms,
        )
    except AssertionError:
        count = await _safe_async(locator.count, 0)
        observed = (
            await _safe_async(
                lambda: locator.first.evaluate(
                    "(element, name) => element[name]",
                    check.property_name,
                ),
                "<unavailable>",
            )
            if count
            else "<element not found>"
        )
    except Exception as error:
        return _evaluation_failure("element property", check.selector, error)
    else:
        count = 1
        observed = await locator.evaluate(
            "(element, name) => element[name]",
            check.property_name,
        )

    expected = (
        f"property {check.property_name!r} of {check.selector!r} "
        f"equals {check.expected!r}"
    )
    passed = count == 1 and observed == check.expected
    return _check_result(
        expected,
        f"property value is {observed!r}",
        passed,
        {
            "expectation_type": "property_equals",
            "selector": check.selector,
            "selector_count": count,
            "property_name": check.property_name,
            "expected": check.expected,
            "observed": observed,
            "timeout_ms": check.timeout_ms,
        },
    )


def _combine_results(results: list[VerificationResult]) -> VerificationResult:
    passed_count = sum(result.passed for result in results)
    total = len(results)
    passed = passed_count == total
    failures = [result.failure_reason for result in results if not result.passed]
    return VerificationResult(
        expected_state=f"all {total} task checks pass",
        observed_state=f"{passed_count} of {total} task checks passed",
        passed=passed,
        evidence={
            "expectation_type": "all_of",
            "checks": [
                {
                    "passed": result.passed,
                    "expected_state": result.expected_state,
                    "observed_state": result.observed_state,
                    "failure_reason": result.failure_reason,
                    "evidence": result.evidence,
                }
                for result in results
            ],
        },
        failure_reason=(
            None
            if passed
            else f"{total - passed_count} of {total} task checks failed: "
            + "; ".join(reason for reason in failures if reason)
        ),
    )


def _check_result(
    expected: str,
    observed: str,
    passed: bool,
    evidence: dict[str, object],
) -> VerificationResult:
    return VerificationResult(
        expected_state=expected,
        observed_state=observed,
        passed=passed,
        evidence=evidence,
        failure_reason=None if passed else f"expected {expected}; observed {observed}",
    )


def _evaluation_failure(
    subject: str,
    selector: str,
    error: Exception,
) -> VerificationResult:
    expected = f"evaluate {subject} for {selector!r}"
    return VerificationResult(
        expected_state=expected,
        observed_state=f"evaluation raised {type(error).__name__}",
        passed=False,
        evidence={
            "expectation_type": "evaluation_error",
            "selector": selector,
            "error_type": type(error).__name__,
        },
        failure_reason=f"could not {expected}: {type(error).__name__}: {error}",
    )


def _url_description(check: UrlMatch) -> str:
    conditions = []
    if check.scheme is not None:
        conditions.append(f"scheme equals {check.scheme!r}")
    if check.host is not None:
        relation = "or a subdomain" if check.allow_subdomains else "exactly"
        conditions.append(f"host equals {check.host!r} {relation}")
    if check.path_prefix is not None:
        conditions.append(f"path starts with {check.path_prefix!r}")
    return "URL where " + " and ".join(conditions)


def _validate_selector(selector: object) -> None:
    if not isinstance(selector, str) or not selector.strip():
        raise ValueError("selector cannot be empty")


def _validate_timeout(timeout_ms: object) -> None:
    if (
        not isinstance(timeout_ms, int)
        or isinstance(timeout_ms, bool)
        or timeout_ms <= 0
    ):
        raise ValueError("timeout_ms must be a positive integer")


def validate_task_expectation(expectation: object) -> None:
    if not isinstance(
        expectation,
        (UrlMatch, ElementVisible, TextMatch, PropertyEquals, AllOf),
    ):
        raise TypeError("task_expectation must be created by a task check helper")


def _is_json_scalar(value: object) -> bool:
    if isinstance(value, float):
        return isfinite(value)
    return value is None or isinstance(value, (str, int, bool))


def _safe_sync(function: object, default: object) -> object:
    try:
        return function()  # type: ignore[operator]
    except Exception:
        return default


async def _safe_async(function: object, default: object) -> object:
    try:
        return await function()  # type: ignore[operator]
    except Exception:
        return default


__all__ = [
    "AllOf",
    "ElementVisible",
    "PropertyEquals",
    "TaskExpectation",
    "TextMatch",
    "UrlMatch",
    "all_of",
    "element_visible",
    "property_equals",
    "text_contains",
    "text_equals",
    "url_matches",
]
