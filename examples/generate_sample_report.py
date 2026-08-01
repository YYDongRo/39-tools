from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path

from agent_devtools import ActionRecord, ActionSession, ActionStatus
from agent_devtools.report import write_session_html
from agent_devtools.verification import VerificationResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "sample-report"
SHOP_ROOT = "https://shop.example.test"
QUERY = "Wireless Headphones"


def _verification(expected: str, observed: str) -> VerificationResult:
    return VerificationResult(
        expected_state=expected,
        observed_state=observed,
        passed=True,
    )


def build_sample_session() -> ActionSession:
    started_at = datetime(2026, 7, 30, 16, 0, tzinfo=UTC)
    screenshots = Path("screenshots")
    actions = [
        ActionRecord(
            action_type="navigate",
            arguments={"url": f"{SHOP_ROOT}/"},
            start_time=started_at,
            duration_ms=184,
            status=ActionStatus.SUCCESS,
            screenshot_before=screenshots / "01-blank.svg",
            screenshot_after=screenshots / "02-shop.svg",
            observations={
                "page_url_before": "about:blank",
                "page_url_after": f"{SHOP_ROOT}/",
            },
            verification=_verification(
                "the product search field is visible",
                "the product search field is visible",
            ),
        ),
        ActionRecord(
            action_type="fill",
            arguments={"selector": "#product-search", "text": QUERY},
            start_time=started_at + timedelta(seconds=1),
            duration_ms=42,
            status=ActionStatus.SUCCESS,
            screenshot_before=screenshots / "02-shop.svg",
            screenshot_after=screenshots / "03-query-filled.svg",
            observations={
                "page_url_before": f"{SHOP_ROOT}/",
                "input_value_after": QUERY,
                "page_url_after": f"{SHOP_ROOT}/",
            },
            verification=_verification(
                f"input '#product-search' equals '{QUERY}'",
                f"input value is '{QUERY}'",
            ),
        ),
        ActionRecord(
            action_type="click",
            arguments={"selector": "#search-button"},
            start_time=started_at + timedelta(seconds=2),
            duration_ms=96,
            status=ActionStatus.SUCCESS,
            screenshot_before=screenshots / "03-query-filled.svg",
            screenshot_after=screenshots / "04-results.svg",
            observations={
                "page_url_before": f"{SHOP_ROOT}/",
                "page_url_after": f"{SHOP_ROOT}/search?q=wireless-headphones",
                "state_before": {"results_visible": False},
                "state_after": {"results_visible": True},
                "state_changes": ["results_visible"],
            },
            verification=_verification(
                "search results are visible",
                "2 search results are visible",
            ),
        ),
        ActionRecord(
            action_type="click",
            arguments={"selector": ".product-card:first-child"},
            start_time=started_at + timedelta(seconds=3),
            duration_ms=73,
            status=ActionStatus.SUCCESS,
            screenshot_before=screenshots / "04-results.svg",
            screenshot_after=screenshots / "05-wrong-product.svg",
            observations={
                "page_url_before": f"{SHOP_ROOT}/search?q=wireless-headphones",
                "page_url_after": f"{SHOP_ROOT}/products/usb-c-cable",
                "clicked_target_text": "USB-C Cable",
            },
        ),
    ]
    task_verification = VerificationResult(
        expected_state=(
            "the product page for 'Wireless Headphones' is open"
        ),
        observed_state="the product page for 'USB-C Cable' is open",
        passed=False,
        failure_reason=(
            "The browser opened a product page, but it was not the product "
            "requested. The final click selected 'USB-C Cable'."
        ),
        evidence={
            "checks": [
                {
                    "passed": True,
                    "expected_state": "a product detail page is open",
                    "observed_state": "a product detail page is open",
                },
                {
                    "passed": False,
                    "expected_state": (
                        "product title contains 'Wireless Headphones'"
                    ),
                    "observed_state": "product title is 'USB-C Cable'",
                },
            ],
            "final_url": f"{SHOP_ROOT}/products/usb-c-cable",
        },
    )
    return ActionSession(
        actions=actions,
        goal=(
            "Search for 'Wireless Headphones' and open the matching "
            "product page."
        ),
        verification_source="deterministic sample checks",
        verification=task_verification,
    )


def _browser_snapshot(
    *,
    url: str,
    heading: str,
    content: str,
    accent: str = "#2563eb",
) -> str:
    safe_url = escape(url)
    safe_heading = escape(heading)
    safe_content = escape(content)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675">
  <rect width="1200" height="675" fill="#f8fafc"/>
  <rect x="30" y="30" width="1140" height="615" rx="18" fill="#ffffff" stroke="#cbd5e1" stroke-width="2"/>
  <rect x="30" y="30" width="1140" height="64" rx="18" fill="#e2e8f0"/>
  <circle cx="68" cy="62" r="9" fill="#f87171"/>
  <circle cx="98" cy="62" r="9" fill="#fbbf24"/>
  <circle cx="128" cy="62" r="9" fill="#4ade80"/>
  <rect x="170" y="46" width="950" height="32" rx="8" fill="#ffffff"/>
  <text x="190" y="68" font-family="Arial, sans-serif" font-size="16" fill="#475569">{safe_url}</text>
  <rect x="80" y="140" width="10" height="112" rx="5" fill="{accent}"/>
  <text x="120" y="185" font-family="Arial, sans-serif" font-size="42" font-weight="700" fill="#0f172a">{safe_heading}</text>
  <text x="120" y="230" font-family="Arial, sans-serif" font-size="24" fill="#475569">{safe_content}</text>
  <rect x="120" y="300" width="760" height="64" rx="10" fill="#f8fafc" stroke="#cbd5e1" stroke-width="2"/>
  <rect x="910" y="300" width="170" height="64" rx="10" fill="{accent}"/>
  <text x="960" y="340" font-family="Arial, sans-serif" font-size="20" font-weight="700" fill="#ffffff">Continue</text>
  <rect x="120" y="410" width="960" height="150" rx="12" fill="#f1f5f9"/>
  <rect x="150" y="442" width="280" height="24" rx="6" fill="#cbd5e1"/>
  <rect x="150" y="486" width="640" height="18" rx="5" fill="#e2e8f0"/>
  <rect x="150" y="522" width="520" height="18" rx="5" fill="#e2e8f0"/>
</svg>
"""


def _snapshot_documents() -> dict[str, str]:
    return {
        "01-blank.svg": _browser_snapshot(
            url="about:blank",
            heading="New browser page",
            content="No site has been opened yet.",
            accent="#64748b",
        ),
        "02-shop.svg": _browser_snapshot(
            url=f"{SHOP_ROOT}/",
            heading="Local Shop",
            content="Search for a product",
        ),
        "03-query-filled.svg": _browser_snapshot(
            url=f"{SHOP_ROOT}/",
            heading="Local Shop",
            content=f"Search: {QUERY}",
        ),
        "04-results.svg": _browser_snapshot(
            url=f"{SHOP_ROOT}/search?q=wireless-headphones",
            heading="Search results",
            content="USB-C Cable · Wireless Headphones",
        ),
        "05-wrong-product.svg": _browser_snapshot(
            url=f"{SHOP_ROOT}/products/usb-c-cable",
            heading="USB-C Cable",
            content="This is not the requested product.",
            accent="#dc2626",
        ),
    }


def generate_sample_report(output_dir: Path = DEFAULT_OUTPUT_DIR) -> list[Path]:
    screenshot_dir = output_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    generated_paths: list[Path] = []
    for filename, document in _snapshot_documents().items():
        path = screenshot_dir / filename
        path.write_text(document, encoding="utf-8")
        generated_paths.append(path)

    report_path = output_dir / "report.html"
    write_session_html(build_sample_session(), report_path)
    generated_paths.append(report_path)
    return generated_paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the sanitized Agent DevTools sample report."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="output directory (default: docs/sample-report)",
    )
    args = parser.parse_args()
    generated = generate_sample_report(args.output)
    print(f"Generated {len(generated)} files in {args.output}")


if __name__ == "__main__":
    main()
