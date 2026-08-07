import json
from dataclasses import dataclass
from html import escape
from pathlib import Path

from agent_devtools.action import ActionOutcome, ActionRecord, ActionStatus
from agent_devtools.analysis import TrajectoryFinding, analyze_session
from agent_devtools.evaluation import DivergenceKind, TrajectoryDivergence
from agent_devtools.failure import FailureCategory
from agent_devtools.serialization import SESSION_SCHEMA_VERSION, action_to_dict
from agent_devtools.session import ActionSession
from agent_devtools.verification import VerificationResult


_PAGE_URL_KEYS = {"page_url_before", "page_url_after"}
_STRUCTURED_STATE_KEYS = {
    "state_before",
    "state_after",
    "state_changes",
    "state_before_error_type",
    "state_after_error_type",
    "observation_finalizer_error_type",
}
_ACTION_EVENT_KEYS = {
    "browser_events",
    "event_collection_start_error_type",
    "event_collection_finish_error_type",
}
_FIELD_LABELS = {
    "diagnostic_error_type": "Diagnostic error",
    "input_value_after": "Input value after",
    "selector": "Selector",
    "selector_count": "Matches",
    "selector_count_after": "Matches after",
    "target_editable": "Editable",
    "target_enabled": "Enabled",
    "target_visible": "Visible",
}
_ARGUMENT_LABELS = {
    "url": "Target URL",
    "selector": "Target",
    "text": "Text",
    "key": "Key",
    "button": "Button",
    "new_tab": "New tab",
    "index": "Element index",
    "timeout_ms": "Timeout",
    "delta_x": "Horizontal scroll",
    "delta_y": "Vertical scroll",
}
_INTERNAL_ARGUMENT_KEYS = {"browser_use_step"}
_FAILURE_SUMMARIES = {
    FailureCategory.TIMEOUT: "The action timed out.",
    FailureCategory.OPERATION_ERROR: "The action returned an operation error.",
    FailureCategory.VERIFICATION_MISMATCH: (
        "The observed state did not match the expected state."
    ),
    FailureCategory.TARGET_NOT_FOUND: "The target was not found.",
    FailureCategory.TARGET_AMBIGUOUS: "More than one target matched.",
    FailureCategory.TARGET_NOT_VISIBLE: "The target was not visible.",
    FailureCategory.TARGET_DISABLED: "The target was disabled.",
    FailureCategory.TARGET_NOT_EDITABLE: "The target was not editable.",
    FailureCategory.UNKNOWN: (
        "The available evidence does not identify a specific cause."
    ),
}


@dataclass(frozen=True)
class ReplayReportSummary:
    """Comparison details shown at the top of a replay session report."""

    target_action_number: int
    source_action: ActionRecord
    replayed_action: ActionRecord | None
    reproduced: bool
    context_failure_action_number: int | None = None
    first_divergence: TrajectoryDivergence | None = None
    target_action_selection_note: str | None = None


@dataclass(frozen=True)
class ReplayStabilityRunSummary:
    """One run in an aggregate replay stability report."""

    run_number: int
    replay_summary: ReplayReportSummary
    report_path: Path


def format_session_summary(
    session: ActionSession,
    report_path: str | Path,
) -> str:
    execution_failures = sum(
        action.status is ActionStatus.FAILURE for action in session.actions
    )
    execution_successes = session.action_count - execution_failures
    lines = ["Agent DevTools"]
    if session.goal is not None:
        lines.append(f"Task: {_compact_console_text(session.goal)}")
    lines.extend(
        (
            f"Task result: {session.outcome.value.upper()}",
            (
                f"Actions: {session.action_count} "
                f"({execution_successes} succeeded, "
                f"{execution_failures} failed)"
            ),
            f"Final check: {_final_check_label(session)}",
        )
    )

    failed_action = next(
        (
            (number, action)
            for number, action in enumerate(session.actions, start=1)
            if action.outcome is ActionOutcome.FAILURE
        ),
        None,
    )
    if failed_action is not None:
        number, action = failed_action
        lines.append(f"Failed at: Action {number} — {action.action_type}")
        category = _outcome_failure_category(action)
        if category is not None:
            lines.append(f"Likely cause: {_FAILURE_SUMMARIES[category]}")
    elif session.verification is not None and not session.verification.passed:
        lines.append("Failed at: Final task check")
        lines.append(
            "Reason: "
            + _compact_console_text(session.verification.failure_reason or "")
        )
    elif session.verification is None and session.verification_note is not None:
        lines.append(
            f"Reason: {_compact_console_text(session.verification_note)}"
        )

    findings = analyze_session(session)
    if findings:
        finding = findings[0]
        action_label = ", ".join(str(number) for number in finding.action_numbers)
        suffix = f" (actions {action_label})" if action_label else ""
        lines.append(f"Potential issue: {finding.title}{suffix}")

    lines.append(f"Report: {Path(report_path).resolve()}")
    return "\n".join(lines)


def _final_check_label(session: ActionSession) -> str:
    if session.verification is None:
        return "not run"
    return "passed" if session.verification.passed else "failed"


def _compact_console_text(value: str, *, limit: int = 160) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _screenshot_panel(title: str, screenshot_path: object) -> str:
    if screenshot_path is None:
        content = '<p class="missing">Not captured</p>'
    else:
        safe_path = escape(str(screenshot_path), quote=True)
        content = f'<img src="{safe_path}" alt="{title} action screenshot">'

    return f"""
        <article class="screenshot">
          <h2>{title}</h2>
          {content}
        </article>"""


def _verification_label(action: ActionRecord) -> str:
    if action.verification is None:
        return "not configured"
    return "passed" if action.verification.passed else "failed"


def _action_status(action: ActionRecord) -> tuple[str, str]:
    if action.outcome is ActionOutcome.FAILURE:
        return "failure", "failed"
    if action.verification is not None:
        return "success", "verified"
    return "neutral", "execution succeeded"


def _verification_result_section(
    verification: VerificationResult,
    title: str,
    *,
    summarize_checks: bool = False,
) -> str:
    status = "passed" if verification.passed else "failed"
    is_ai_assessment = verification.evidence.get("assessment_type") in {
        "ai_final_state",
        "ai_trajectory",
    }
    evidence_section = _verification_evidence_section(
        verification,
        summarize_check=summarize_checks,
    )

    failure_section = ""
    if verification.failure_reason is not None and not is_ai_assessment:
        category_section = ""
        if verification.failure_category is not None:
            category_section = (
                "<p><strong>Category:</strong> "
                f"{escape(verification.failure_category.value)}</p>"
            )
        failure_section = f"""
        <div class="verification-failure">
          {category_section}
          <p>{escape(verification.failure_reason)}</p>
        </div>"""

    if summarize_checks:
        assessment_summary = ""
        if is_ai_assessment:
            assessment_summary = (
                '<details class="assessment-summary">'
                "<summary>Judge explanation</summary>"
                f"<p>{escape(verification.observed_state)}</p>"
                "</details>"
            )
        overview = f"""
        <div class="verification-heading">
          <h2>{escape(title)}</h2>
          <span class="check-total check-total-{status}">{status}</span>
        </div>
        {assessment_summary}"""
    else:
        overview = f"""
        <h2>{escape(title)}</h2>
        <dl>
          <div><dt>Status</dt><dd>{status}</dd></div>
          <div><dt>Expected state</dt><dd>{escape(verification.expected_state)}</dd></div>
          <div><dt>Observed state</dt><dd>{escape(verification.observed_state)}</dd></div>
        </dl>"""

    return f"""
      <section class="verification">
        {overview}
        {failure_section}
        {evidence_section}
      </section>"""


def _verification_evidence_section(
    verification: VerificationResult,
    *,
    summarize_check: bool,
) -> str:
    if not verification.evidence:
        return ""

    if verification.evidence.get("assessment_type") == "ai_final_state":
        facts = verification.evidence.get("facts")
        fact_items = ""
        if isinstance(facts, list) and all(
            isinstance(fact, str) for fact in facts
        ):
            fact_items = "".join(
                f"<li>{escape(fact)}</li>" for fact in facts
            )
        final_page = verification.evidence.get("final_page")
        final_page_json = escape(
            json.dumps(final_page, ensure_ascii=False, indent=2)
        )
        return f"""
        <div class="assessment-evidence">
          <h3>Evidence used</h3>
          <ul>{fact_items or '<li>No specific page fact was returned.</li>'}</ul>
        </div>
        <details class="verification-evidence">
          <summary>Final page snapshot</summary>
          <pre>{final_page_json}</pre>
        </details>"""

    evidence = escape(
        json.dumps(verification.evidence, ensure_ascii=False, indent=2)
    )
    checks = verification.evidence.get("checks")
    if not isinstance(checks, list) or not all(
        isinstance(check, dict) for check in checks
    ):
        if not summarize_check:
            return f"<h3>Verification evidence</h3><pre>{evidence}</pre>"
        checks = [
            {
                "passed": verification.passed,
                "expected_state": verification.expected_state,
                "observed_state": verification.observed_state,
            }
        ]

    check_items = []
    for index, check in enumerate(checks, start=1):
        passed = check.get("passed") is True
        check_status = "passed" if passed else "failed"
        expected = escape(str(check.get("expected_state", "—")))
        observed = escape(str(check.get("observed_state", "—")))
        check_items.append(
            f"""
          <li class="verification-check verification-check-{check_status}">
            <div>
              <strong>Check {index}</strong>
              <span class="check-status">{check_status}</span>
            </div>
            <p>{expected}</p>
            <small>Observed: {observed}</small>
          </li>"""
        )

    return f"""
        <div class="verification-check-list">
          <h3>Checks</h3>
          <ol>{''.join(check_items)}
          </ol>
        </div>
        <details class="verification-evidence">
          <summary>Full verification evidence</summary>
          <pre>{evidence}</pre>
        </details>"""


def _verification_section(action: ActionRecord) -> str:
    verification = action.verification
    if verification is None:
        return ""
    return _verification_result_section(verification, "Verification")


def _observations_section(action: ActionRecord) -> str:
    observations_without_urls = {
        key: value
        for key, value in action.observations.items()
        if (
            (key not in _PAGE_URL_KEYS or not isinstance(value, str))
            and key not in _STRUCTURED_STATE_KEYS
            and key not in _ACTION_EVENT_KEYS
        )
    }
    if not observations_without_urls:
        return ""
    return f"""
      <section class="observations">
        <h2>Observations</h2>
        {_key_value_grid(observations_without_urls)}
      </section>"""


def _structured_state_section(action: ActionRecord) -> str:
    observations = action.observations
    if not any(key in observations for key in _STRUCTURED_STATE_KEYS):
        return ""

    changes = observations.get("state_changes")
    if isinstance(changes, list):
        if changes:
            change_items = "".join(
                f"<li>{escape(str(change))}</li>" for change in changes
            )
            change_content = f"<ul>{change_items}</ul>"
        else:
            change_content = (
                '<p class="missing">No structured state changes detected.</p>'
            )
    else:
        change_content = (
            '<p class="missing">State changes unavailable.</p>'
        )

    error_content = ""
    for label, key in (
        ("Before", "state_before_error_type"),
        ("After", "state_after_error_type"),
        ("Finalizer", "observation_finalizer_error_type"),
    ):
        error_type = observations.get(key)
        if isinstance(error_type, str):
            error_content += (
                '<p class="missing">'
                f"{label} observation unavailable ({escape(error_type)})."
                "</p>"
            )

    snapshots = ""
    for label, key in (
        ("State before", "state_before"),
        ("State after", "state_after"),
    ):
        state = observations.get(key)
        if isinstance(state, dict):
            encoded_state = escape(
                json.dumps(state, ensure_ascii=False, indent=2)
            )
            snapshots += f"""
        <details class="state-snapshot">
          <summary>{label}</summary>
          <pre>{encoded_state}</pre>
        </details>"""

    return f"""
      <section class="structured-state">
        <h2>Structured state</h2>
        <h3>Detected changes</h3>
        {change_content}
        {error_content}
        {snapshots}
      </section>"""


def _browser_events_section(action: ActionRecord) -> str:
    events = action.observations.get("browser_events")
    if not isinstance(events, list) or not events:
        return ""
    event_count = sum(
        event.get("count", 1)
        for event in events
        if isinstance(event, dict)
        and isinstance(event.get("count", 1), int)
    )
    encoded_events = escape(
        json.dumps(events, ensure_ascii=False, indent=2)
    )
    event_label = "event" if event_count == 1 else "events"
    return f"""
      <section class="browser-evidence">
        <details>
          <summary>Browser evidence ({event_count} {event_label})</summary>
          <pre>{encoded_events}</pre>
        </details>
      </section>"""


def _auxiliary_events_section(session: ActionSession) -> str:
    if not session.auxiliary_events:
        return ""

    event_items = []
    for event in session.auxiliary_events:
        action_type = escape(str(event.get("action_type", "unknown")))
        status = escape(str(event.get("status", "observed")))
        arguments = escape(
            json.dumps(event.get("arguments", {}), ensure_ascii=False, indent=2)
        )
        event_items.append(
            f"""<li><div><strong>{action_type}</strong>
              <span class="auxiliary-status">{status}</span></div>
              <pre>{arguments}</pre></li>"""
        )

    return f"""
        <details class="auxiliary-events">
          <summary>Agent auxiliary events ({len(session.auxiliary_events)})</summary>
          <p>Planning and file operations are kept outside the browser action timeline.</p>
          <ol>{''.join(event_items)}</ol>
        </details>"""


def _coverage_warning_section(session: ActionSession) -> str:
    if session.action_count:
        return ""

    if session.auxiliary_events:
        detail = (
            "Only auxiliary events were recorded; no browser action appears "
            "in the action timeline."
        )
    elif session.verification_source == "agent-run":
        detail = (
            "The run ended before a browser action was captured. Check the "
            "agent-run note above for the stopping point."
        )
    elif session.verification is not None and session.verification.passed:
        detail = (
            "The final check passed, but no browser action was captured. "
            "This does not prove that the task was fully observed."
        )
    else:
        detail = (
            "The agent may have ended before acting or used a call outside "
            "the supported recording boundary."
        )

    return f"""
      <section class="coverage-warning" aria-labelledby="coverage-title">
        <div class="coverage-heading">
          <div>
            <p class="eyebrow">Recording coverage</p>
            <h2 id="coverage-title">No browser actions captured</h2>
          </div>
          <span class="coverage-badge">Limited evidence</span>
        </div>
        <p>{escape(detail)}</p>
        <p class="coverage-boundary">
          Only calls routed through a supported observer appear in this timeline.
        </p>
      </section>"""


def _key_value_grid(values: dict[str, object]) -> str:
    items = "".join(
        "<div><dt>"
        f"{escape(_FIELD_LABELS.get(key, key.replace('_', ' ').title()))}"
        "</dt><dd>"
        f"{_display_value(value)}"
        "</dd></div>"
        for key, value in values.items()
    )
    return f'<dl class="key-value-grid">{items}</dl>'


def _arguments_content(arguments: object, *, include_raw: bool = True) -> str:
    encoded_arguments = escape(
        json.dumps(arguments, ensure_ascii=False, indent=2)
    )
    visible_arguments: dict[str, object] = {}
    if isinstance(arguments, dict):
        for key, value in arguments.items():
            if not isinstance(key, str) or key in _INTERNAL_ARGUMENT_KEYS:
                continue
            label = _ARGUMENT_LABELS.get(key, key.replace("_", " ").title())
            if label in visible_arguments:
                label = f"{label} ({key})"
            visible_arguments[label] = value

    if visible_arguments:
        items = "".join(
            "<div><dt>"
            f"{escape(key)}"
            "</dt><dd>"
            f"{_display_value(value)}"
            "</dd></div>"
            for key, value in visible_arguments.items()
        )
        summary = f'<dl class="key-value-grid">{items}</dl>'
    else:
        summary = '<p class="missing">No user-facing arguments.</p>'

    if not include_raw:
        return summary

    return f"""
        {summary}
        <details class="technical-details">
          <summary>Technical details</summary>
          <pre>{encoded_arguments}</pre>
        </details>""".strip()


def _display_value(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '""' if not value else escape(value)
    return escape(json.dumps(value, ensure_ascii=False))


def _failure_content(action: ActionRecord) -> str:
    if action.failure_reason is None:
        return ""

    category_section = ""
    if action.failure_category is not None:
        category_section = (
            "<p><strong>Category:</strong> "
            f"{escape(action.failure_category.value)}</p>"
        )

    reason = action.failure_reason
    summary = reason.splitlines()[0] if reason.splitlines() else reason
    raw_details = ""
    if "\n" in reason:
        raw_details = f"""
        <details class="raw-error">
          <summary>Raw error details</summary>
          <pre>{escape(reason)}</pre>
        </details>"""

    evidence_section = ""
    if action.failure_evidence:
        evidence_section = f"""
        <h3>Diagnostic evidence</h3>
        {_key_value_grid(action.failure_evidence)}"""

    return f"""
        {category_section}
        <p class="error-summary">{escape(summary)}</p>
        {raw_details}
        {evidence_section}"""


def _page_url_details(action: ActionRecord) -> str:
    before = action.observations.get("page_url_before")
    after = action.observations.get("page_url_after")
    if not isinstance(before, str) and not isinstance(after, str):
        return ""
    if before == after and isinstance(before, str):
        return f"<div><dt>Page URL</dt><dd>{escape(before)}</dd></div>"

    details = []
    if isinstance(before, str):
        details.append(
            f"<div><dt>Page URL before</dt><dd>{escape(before)}</dd></div>"
        )
    if isinstance(after, str):
        details.append(
            f"<div><dt>Page URL after</dt><dd>{escape(after)}</dd></div>"
        )
    return "".join(details)


def _outcome_failure_category(action: ActionRecord) -> FailureCategory | None:
    if action.status is ActionStatus.FAILURE:
        return action.failure_category
    if action.verification is not None and not action.verification.passed:
        return action.verification.failure_category
    return None


def _trajectory_findings_section(session: ActionSession) -> str:
    findings = analyze_session(session)
    if not findings:
        return ""

    finding_cards = "\n".join(
        _trajectory_finding_card(finding) for finding in findings
    )
    warning_label = "warning" if len(findings) == 1 else "warnings"
    return f"""
      <section class="trajectory-findings" aria-labelledby="findings-title">
        <div class="findings-heading">
          <div>
            <p class="eyebrow">Automatic analysis</p>
            <h2 id="findings-title">Potential issues</h2>
          </div>
          <span class="findings-count">{len(findings)} {warning_label}</span>
        </div>
        <p class="findings-note">These warnings highlight suspicious patterns.
          They do not change the recorded task outcome.</p>
        <div class="finding-list">
{finding_cards}
        </div>
      </section>"""


def _trajectory_finding_card(finding: TrajectoryFinding) -> str:
    action_links = ", ".join(
        f'<a href="#action-{number}">Action {number}</a>'
        for number in finding.action_numbers
    )
    evidence = escape(
        json.dumps(finding.evidence, ensure_ascii=False, indent=2)
    )
    suggestion_items = "".join(
        f"<li>{escape(suggestion)}</li>"
        for suggestion in finding.suggestions
    )
    likely_cause = ""
    if finding.likely_cause is not None:
        likely_cause = (
            '<p class="likely-cause"><strong>Likely cause:</strong> '
            f"{escape(finding.likely_cause)}</p>"
        )
    return f"""
          <article class="finding-card">
            <div class="finding-title-row">
              <span class="warning-label">Warning</span>
              <h3>{escape(finding.title)}</h3>
            </div>
            <p class="finding-summary">{escape(finding.summary)}</p>
            {likely_cause}
            <p class="finding-actions"><strong>Related:</strong>
              {action_links}</p>
            <details class="finding-details">
              <summary>Evidence and what to inspect</summary>
              <pre>{evidence}</pre>
              <ul>{suggestion_items}</ul>
            </details>
          </article>"""


def write_action_html(action: ActionRecord, output_path: Path) -> None:
    data = action_to_dict(action)
    execution_status = escape(str(data["status"]))
    outcome = escape(action.outcome.value)
    display_status, display_label = _action_status(action)
    verification_status = _verification_label(action)
    failure_section = ""
    failure_content = _failure_content(action)
    if failure_content:
        failure_section = f"""
      <section class="failure">
        <h2>Failure reason</h2>
        {failure_content}
      </section>"""
    verification_section = _verification_section(action)
    observations_section = _observations_section(action)
    structured_state_section = _structured_state_section(action)
    browser_events_section = _browser_events_section(action)
    page_url_details = _page_url_details(action)

    document = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Action trace: {escape(str(data["action_type"]))}</title>
    <style>
      :root {{ color-scheme: light; font-family: system-ui, sans-serif; }}
      body {{ background: #f3f4f6; color: #0f172a; margin: 0; }}
      main {{ margin: 0 auto; max-width: 1200px; padding: 40px 24px; }}
      header, section, article {{ background: white; border-radius: 12px; }}
      header, section {{ margin-bottom: 24px; padding: 24px; }}
      h1, h2, p {{ margin-top: 0; }}
      .eyebrow {{ color: #64748b; font-size: 14px; font-weight: 700; }}
      .title-row {{ align-items: center; display: flex; gap: 16px; }}
      .title-row h1 {{ margin-bottom: 0; }}
      .status {{ border-radius: 999px; font-weight: 700; padding: 6px 12px; }}
      .status-success {{ background: #dcfce7; color: #166534; }}
      .status-failure {{ background: #fee2e2; color: #991b1b; }}
      .status-unverified {{ background: #fef3c7; color: #92400e; }}
      .status-neutral {{ background: #e0f2fe; color: #075985; }}
      dl {{ display: grid; gap: 20px; grid-template-columns: repeat(4, 1fr); }}
      dt {{ color: #64748b; font-size: 13px; font-weight: 700; }}
      dd {{ margin: 6px 0 0; overflow-wrap: anywhere; }}
      pre {{ background: #0f172a; border-radius: 8px; color: #e2e8f0;
             overflow-x: auto; padding: 16px; }}
      .failure {{ background: #fff1f2; border: 1px solid #fecdd3; }}
      .failure p {{ white-space: pre-wrap; }}
      .key-value-grid {{ background: rgba(255, 255, 255, .72);
                         border-radius: 8px; grid-template-columns:
                         repeat(auto-fit, minmax(140px, 1fr)); margin: 0;
                         padding: 16px; }}
      .raw-error {{ margin-top: 16px; }}
      .raw-error summary {{ cursor: pointer; font-weight: 700; }}
      .raw-error pre {{ margin-bottom: 0; }}
      .technical-details {{ margin-top: 14px; }}
      .technical-details summary {{ cursor: pointer; font-weight: 700; }}
      .technical-details pre {{ margin: 10px 0 0; }}
      .verification {{ border: 1px solid #cbd5e1; }}
      .verification-failure {{ background: #fff1f2; border-radius: 8px;
                               margin-top: 20px; padding: 16px; }}
      .verification-failure p {{ margin-bottom: 0; white-space: pre-wrap; }}
      .screenshots {{ background: transparent; display: grid; gap: 24px;
                      grid-template-columns: repeat(2, minmax(0, 1fr)); padding: 0; }}
      .screenshot {{ padding: 20px; }}
      .screenshot img {{ border: 1px solid #e2e8f0; border-radius: 8px;
                         display: block; height: auto; width: 100%; }}
      .missing {{ color: #64748b; }}
      @media (max-width: 800px) {{
        dl, .screenshots {{ grid-template-columns: 1fr; }}
      }}
    </style>
  </head>
  <body>
    <main>
      <header>
        <p class="eyebrow">Agent DevTools · Schema {data["schema_version"]}</p>
        <div class="title-row">
          <h1>{escape(str(data["action_type"]))}</h1>
          <span class="status status-{display_status}">{display_label}</span>
        </div>
      </header>
      <section>
        <h2>Action details</h2>
        <dl>
          <div><dt>Recorded outcome</dt><dd>{outcome}</dd></div>
          <div><dt>Execution status</dt><dd>{execution_status}</dd></div>
          <div><dt>Verification status</dt><dd>{verification_status}</dd></div>
          <div><dt>Start time</dt><dd>{escape(str(data["start_time"]))}</dd></div>
          <div><dt>Duration</dt><dd>{data["duration_ms"]} ms</dd></div>
          {page_url_details}
          <div><dt>Before screenshot</dt><dd>{escape(str(data["screenshot_before"] or "—"))}</dd></div>
          <div><dt>After screenshot</dt><dd>{escape(str(data["screenshot_after"] or "—"))}</dd></div>
        </dl>
      </section>
      <section>
        <h2>Arguments</h2>
        {_arguments_content(data["arguments"])}
      </section>{observations_section}{structured_state_section}{browser_events_section}{failure_section}{verification_section}
      <section class="screenshots">
{_screenshot_panel("Before", data["screenshot_before"])}
{_screenshot_panel("After", data["screenshot_after"])}
      </section>
    </main>
  </body>
</html>
"""

    _write_utf8_text(output_path, document)


def _session_action_card(index: int, action: ActionRecord) -> str:
    data = action_to_dict(action)
    execution_status = escape(str(data["status"]))
    display_status, display_label = _action_status(action)
    verification_status = _verification_label(action)
    failure_section = ""
    failure_content = _failure_content(action)
    if failure_content:
        failure_section = f"""
            <div class="failure">
              <strong>Failure reason</strong>
              {failure_content}
            </div>"""
    verification_section = _verification_section(action)
    observations_section = _observations_section(action)
    structured_state_section = _structured_state_section(action)
    browser_events_section = _browser_events_section(action)
    page_url_details = _page_url_details(action)

    screenshots = []
    for label, path in (
        ("Before", data["screenshot_before"]),
        ("After", data["screenshot_after"]),
    ):
        if path is not None:
            safe_path = escape(str(path), quote=True)
            screenshots.append(
                f"""
              <figure>
                <figcaption>{label}</figcaption>
                <a href="{safe_path}">
                  <img src="{safe_path}" alt="{label} action {index} screenshot">
                </a>
              </figure>"""
            )
    screenshot_section = "".join(screenshots)
    if not screenshot_section:
        screenshot_section = '<p class="missing">No screenshots captured.</p>'

    return f"""
        <article class="timeline-item" id="action-{index}">
          <div class="marker">{index}</div>
          <div class="action-card">
            <div class="action-heading">
              <div>
                <p class="eyebrow">Action {index}</p>
                <h2>{escape(str(data["action_type"]))}</h2>
              </div>
              <span class="status status-{display_status}">{display_label}</span>
            </div>
            <dl>
              <div><dt>Execution</dt><dd>{execution_status}</dd></div>
              <div><dt>Action check</dt><dd>{verification_status}</dd></div>
              <div><dt>Start time</dt><dd>{escape(str(data["start_time"]))}</dd></div>
              <div><dt>Duration</dt><dd>{data["duration_ms"]} ms</dd></div>
              {page_url_details}
            </dl>
            <section class="action-evidence" aria-labelledby="action-{index}-evidence-title">
              <div class="action-evidence-heading">
                <div>
                  <h3 id="action-{index}-evidence-title">Visual evidence</h3>
                  <p class="section-note">What changed around this action.</p>
                </div>
                <span class="evidence-flow">Before → After</span>
              </div>
              <div class="action-screenshots">{screenshot_section}
              </div>
            </section>{failure_section}{verification_section}
            <details class="action-technical">
              <summary>Technical details</summary>
              <div class="action-technical-content">
                <div class="technical-details">
                  <section class="technical-group">
                    <h3>Action inputs</h3>
                    <p class="section-note">Values sent to the browser action.</p>
                    {_arguments_content(data["arguments"], include_raw=False)}
                    <pre>{escape(json.dumps(data["arguments"], ensure_ascii=False, indent=2))}</pre>
                  </section>{observations_section}{structured_state_section}{browser_events_section}
                </div>
              </div>
            </details>
          </div>
        </article>"""


def _replay_action_label(action: ActionRecord | None) -> str:
    if action is None:
        return "not run"
    if action.status is ActionStatus.SUCCESS:
        return "success"

    category = action.failure_category
    if category is None and action.verification is not None:
        category = action.verification.failure_category
    if category is None:
        return "failure"
    return f"failure · {category.value}"


def _replay_context_detail(summary: ReplayReportSummary) -> str:
    if summary.context_failure_action_number is not None:
        return (
            "Stopped before target action "
            f"{summary.target_action_number} at context action "
            f"{summary.context_failure_action_number}."
        )

    context_count = max(summary.target_action_number - 1, 0)
    return (
        f"{context_count} preceding action"
        f"{'s' if context_count != 1 else ''} rebuilt."
    )


def _replay_target_selection_detail(summary: ReplayReportSummary) -> str:
    if summary.target_action_selection_note is None:
        return ""
    return (
        "<div><dt>Selection</dt><dd>"
        f"{escape(summary.target_action_selection_note)}"
        "</dd></div>"
    )


_REPLAY_DIVERGENCE_LABELS = {
    DivergenceKind.ACTION_TYPE: "action type differed",
    DivergenceKind.ARGUMENTS: "arguments differed",
    DivergenceKind.EXECUTION_STATUS: "execution status differed",
    DivergenceKind.ACTION_VERIFICATION: "action check differed",
    DivergenceKind.PAGE_URL: "page URL differed",
    DivergenceKind.BROWSER_ERROR: "browser error differed",
    DivergenceKind.STATE: "page state differed",
    DivergenceKind.TRAJECTORY_FINDING: "trajectory finding differed",
    DivergenceKind.MISSING_ACTION: "replay ended early",
    DivergenceKind.EXTRA_ACTION: "replay added an action",
    DivergenceKind.FINAL_VERIFICATION: "final check differed",
}


def _replay_divergence_label(
    divergence: TrajectoryDivergence | None,
    *,
    reproduced: bool,
) -> str:
    if divergence is None:
        return "No trajectory difference." if reproduced else "Target outcome differed."
    location = (
        f"Action {divergence.action_number}"
        if divergence.action_number is not None
        else "Final result"
    )
    label = _REPLAY_DIVERGENCE_LABELS[divergence.kind]
    return f"{location} · {label}."


def _replay_divergence_section(summary: ReplayReportSummary) -> str:
    divergence = summary.first_divergence
    if divergence is None:
        return ""
    label = _replay_divergence_label(
        divergence,
        reproduced=summary.reproduced,
    )
    baseline = escape(
        json.dumps(
            divergence.baseline,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    observed = escape(
        json.dumps(
            divergence.observed,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )
    return f"""
          <details class="replay-divergence">
            <summary>First difference · {escape(label)}</summary>
            <p>{escape(divergence.summary)}</p>
            <div class="replay-divergence-values">
              <div><strong>Original</strong><pre>{baseline}</pre></div>
              <div><strong>Replay</strong><pre>{observed}</pre></div>
            </div>
          </details>"""


def _replay_summary_section(summary: ReplayReportSummary) -> str:
    verdict = "Reproduced" if summary.reproduced else "Not reproduced"
    verdict_class = "reproduced" if summary.reproduced else "not-reproduced"
    verdict_detail = (
        "The replay matched the original target outcome."
        if summary.reproduced
        else "The replay did not match the original target outcome."
    )
    context_detail = _replay_context_detail(summary)
    selection_detail = _replay_target_selection_detail(summary)
    divergence_section = _replay_divergence_section(summary)

    return f"""
        <section class="replay-summary replay-summary-{verdict_class}">
          <div class="replay-summary-heading">
            <div>
              <span class="result-kicker">Replay verdict</span>
              <strong class="replay-verdict">{verdict}</strong>
              <p class="result-detail">{verdict_detail}</p>
            </div>
            <span class="replay-verdict-mark" aria-hidden="true">
              {'✓' if summary.reproduced else '!'}
            </span>
          </div>
          <dl class="replay-comparison">
            <div>
              <dt>Target action</dt>
              <dd>Action {summary.target_action_number}</dd>
            </div>
            <div>
              <dt>Original target</dt>
              <dd>{escape(_replay_action_label(summary.source_action))}</dd>
            </div>
            <div>
              <dt>Replay target</dt>
              <dd>{escape(_replay_action_label(summary.replayed_action))}</dd>
            </div>
            <div>
              <dt>Context</dt>
              <dd>{escape(context_detail)}</dd>
            </div>
            {selection_detail}
          </dl>
          {divergence_section}
        </section>"""


def _safe_replay_report_path(path: Path) -> str:
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("replay report links must be relative paths")
    return escape(path.as_posix(), quote=True)


def _replay_stability_title(
    source_action: ActionRecord,
    reproduced_count: int,
    run_count: int,
) -> tuple[str, str, str]:
    if reproduced_count == run_count:
        if source_action.status is ActionStatus.FAILURE:
            return (
                "Failure reproduced every time",
                "stable",
                "The recorded failure matched in every replay.",
            )
        return (
            "Outcome matched every time",
            "stable",
            "The recorded target outcome matched in every replay.",
        )
    if reproduced_count == 0:
        if source_action.status is ActionStatus.FAILURE:
            return (
                "Failure not reproduced",
                "not-reproduced",
                "None of the replays matched the recorded failure.",
            )
        return (
            "Outcome changed every time",
            "not-reproduced",
            "None of the replays matched the recorded target outcome.",
        )
    return (
        "Intermittent replay result",
        "intermittent",
        "Only some replays matched the recorded target outcome.",
    )


def write_replay_stability_html(
    output_path: Path,
    *,
    target_action_number: int,
    source_action: ActionRecord,
    runs: tuple[ReplayStabilityRunSummary, ...],
    target_action_selection_note: str | None = None,
) -> None:
    if not runs:
        raise ValueError("replay stability reports require at least one run")

    reproduced_count = sum(
        run.replay_summary.reproduced for run in runs
    )
    run_count = len(runs)
    title, status, detail = _replay_stability_title(
        source_action,
        reproduced_count,
        run_count,
    )
    rows = []
    for run in runs:
        summary = run.replay_summary
        verdict = "reproduced" if summary.reproduced else "not reproduced"
        verdict_class = "passed" if summary.reproduced else "failed"
        first_difference = _replay_divergence_label(
            summary.first_divergence,
            reproduced=summary.reproduced,
        )
        report_link = _safe_replay_report_path(run.report_path)
        rows.append(
            f"""
          <tr>
            <td><strong>{run.run_number}</strong></td>
            <td><span class="pill {verdict_class}">{verdict}</span></td>
            <td>{escape(_replay_action_label(summary.source_action))}</td>
            <td>{escape(_replay_action_label(summary.replayed_action))}</td>
            <td><span class="difference-label">{escape(first_difference)}</span></td>
            <td><a href="{report_link}">Open report</a></td>
          </tr>"""
        )

    selection_detail = ""
    if target_action_selection_note is not None:
        selection_detail = (
            "<div><dt>Selection</dt><dd>"
            f"{escape(target_action_selection_note)}"
            "</dd></div>"
        )

    document = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Replay stability</title>
    <style>
      :root {{ color-scheme: light; font-family: system-ui, sans-serif; }}
      * {{ box-sizing: border-box; }}
      body {{ background: #f8fafc; color: #0f172a; margin: 0; }}
      main {{ margin: 0 auto; max-width: 1120px; padding: 48px 24px; }}
      section {{ background: white; border: 1px solid #e2e8f0;
                 border-radius: 16px; margin-bottom: 20px; padding: 28px; }}
      .eyebrow {{ color: #64748b; font-size: 13px; font-weight: 800;
                  letter-spacing: .06em; text-transform: uppercase; }}
      h1, h2, p {{ margin-top: 0; }}
      h1 {{ font-size: 30px; margin-bottom: 8px; }}
      h2 {{ font-size: 19px; }}
      .hero {{ border-left: 6px solid #64748b; }}
      .hero-stable {{ background: #f0fdf4; border-color: #86efac;
                      border-left-color: #16a34a; }}
      .hero-intermittent {{ background: #fffbeb; border-color: #fcd34d;
                            border-left-color: #d97706; }}
      .hero-not-reproduced {{ background: #f1f5f9; border-color: #cbd5e1;
                              border-left-color: #64748b; }}
      .detail {{ color: #475569; line-height: 1.5; }}
      .metrics {{ display: grid; gap: 12px;
                  grid-template-columns: repeat(3, minmax(0, 1fr));
                  margin-top: 22px; }}
      .metric {{ background: rgba(255, 255, 255, .72); border: 1px solid #e2e8f0;
                 border-radius: 10px; padding: 14px 16px; }}
      .metric span {{ color: #64748b; display: block; font-size: 12px;
                      font-weight: 700; margin-bottom: 5px; }}
      .metric strong {{ font-size: 18px; }}
      .pill {{ border-radius: 999px; font-size: 12px; font-weight: 800;
               padding: 5px 9px; text-transform: uppercase; }}
      .passed {{ background: #dcfce7; color: #166534; }}
      .failed {{ background: #fee2e2; color: #991b1b; }}
      .difference-label {{ color: #334155; font-weight: 600; }}
      .table-wrap {{ overflow-x: auto; }}
      table {{ border-collapse: collapse; width: 100%; }}
      th, td {{ border-bottom: 1px solid #e2e8f0; padding: 13px 10px;
                text-align: left; vertical-align: top; }}
      th {{ color: #64748b; font-size: 12px; letter-spacing: .04em;
            text-transform: uppercase; }}
      td {{ font-size: 14px; }}
      a {{ color: #1d4ed8; font-weight: 700; }}
      .target {{ display: grid; gap: 16px; grid-template-columns: repeat(2, 1fr); }}
      dt {{ color: #64748b; font-size: 12px; font-weight: 700; }}
      dd {{ margin: 5px 0 0; overflow-wrap: anywhere; }}
      @media (max-width: 760px) {{
        .metrics, .target {{ grid-template-columns: 1fr; }}
      }}
    </style>
  </head>
  <body>
    <main>
      <section class="hero hero-{status}">
        <p class="eyebrow">Agent DevTools · Replay stability</p>
        <h1>{escape(title)}</h1>
        <p class="detail">{escape(detail)}</p>
        <div class="metrics" aria-label="Replay stability summary">
          <div class="metric"><span>Total replays</span>
            <strong>{run_count}</strong></div>
          <div class="metric"><span>Reproduced</span>
            <strong>{reproduced_count}</strong></div>
          <div class="metric"><span>Not reproduced</span>
            <strong>{run_count - reproduced_count}</strong></div>
        </div>
      </section>
      <section>
        <h2>Target action</h2>
        <dl class="target">
          <div><dt>Action number</dt><dd>{target_action_number}</dd></div>
          <div><dt>Original outcome</dt>
            <dd>{escape(_replay_action_label(source_action))}</dd></div>
          {selection_detail}
        </dl>
      </section>
      <section>
        <h2>Replay runs</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Run</th><th>Verdict</th><th>Original</th>
              <th>Replay</th><th>First difference</th><th>Trace</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
      </section>
    </main>
  </body>
</html>
"""
    _write_utf8_text(output_path, document)


def write_session_html(
    session: ActionSession,
    output_path: Path,
    *,
    replay_summary: ReplayReportSummary | None = None,
) -> None:
    execution_success_count = sum(
        action.status is ActionStatus.SUCCESS for action in session.actions
    )
    failure_count = sum(
        action.outcome is ActionOutcome.FAILURE for action in session.actions
    )
    checked_action_count = sum(
        action.verification is not None for action in session.actions
    )
    unverified_count = sum(
        action.outcome is ActionOutcome.UNVERIFIED for action in session.actions
    )
    category_counts = {
        category: sum(
            _outcome_failure_category(action) is category
            for action in session.actions
        )
        for category in FailureCategory
    }
    if session.verification is not None:
        overall_status = session.outcome.value
    elif session.goal is not None:
        overall_status = "unverified"
    elif session.action_count == 0:
        overall_status = "empty"
    elif session.has_failures:
        overall_status = "failure"
    elif unverified_count:
        overall_status = "neutral"
    else:
        overall_status = "success"

    if session.outcome is ActionOutcome.SUCCESS:
        result_title = "Successful"
        result_detail = "Final task check passed."
    elif session.outcome is ActionOutcome.FAILURE:
        result_title = "Failed"
        failure_reason = (
            session.verification.failure_reason
            if session.verification is not None
            else None
        )
        result_detail = (
            "Final task check failed: "
            + _compact_console_text(failure_reason, limit=180)
            if failure_reason
            else "Final task check failed."
        )
    elif session.verification_source == "agent-run":
        result_title = "Agent run failed"
        result_detail = (
            session.verification_note
            or "The agent stopped before final task verification."
        )
    elif session.action_count == 0:
        result_title = "No actions"
        result_detail = "Nothing was recorded in this run."
    elif session.goal is not None:
        result_title = "Not verified"
        result_detail = "No final task check was completed."
    elif session.has_failures:
        result_title = "Completed with failures"
        result_detail = f"{failure_count} action failures were recorded."
    else:
        result_title = "Execution completed"
        result_detail = "All recorded actions executed successfully."

    if checked_action_count == 0:
        step_check_value = "Not configured"
    elif checked_action_count == session.action_count:
        step_check_value = f"{checked_action_count} run"
    else:
        step_check_value = (
            f"{checked_action_count} of {session.action_count} run"
        )
    report_title = "Task run" if session.goal is not None else "Action session"
    result_mark = {
        "success": "✓",
        "failure": "×",
        "unverified": "?",
        "empty": "—",
        "neutral": "•",
    }[overall_status]
    failure_summary = ""
    if failure_count:
        category_items = "\n".join(
            f"<li><span>{escape(category.value)}</span><strong>{count}</strong></li>"
            for category, count in category_counts.items()
            if count
        )
        failure_summary = f"""
        <section class="failure-summary">
          <h2>Failure categories</h2>
          <ul>{category_items}</ul>
        </section>"""
    cards = "\n".join(
        _session_action_card(index, action)
        for index, action in enumerate(session.actions, start=1)
    )
    if not cards:
        cards = '<section class="empty-state">No actions recorded.</section>'
    goal_section = ""
    if session.goal is not None:
        goal_section = (
            '<p class="goal"><strong>User request:</strong> '
            f"{escape(session.goal)}</p>"
        )
    inferred_goal_section = ""
    if session.inferred_goal is not None:
        inferred_goal_section = (
            '<p><strong>Inferred goal:</strong> '
            f"{escape(session.inferred_goal)}</p>"
        )
    automatic_verification_section = ""
    if (
        session.verification_source is not None
        or session.verification_note is not None
    ):
        source = (
            escape(session.verification_source)
            if session.verification_source is not None
            else "Unavailable"
        )
        context_content = f"{inferred_goal_section}<p><strong>Source:</strong> {source}</p>"
        automatic_verification_section = f"""
        <details class="verification-context">
          <summary>Verification context</summary>
          {context_content}
        </details>"""
        inferred_goal_section = ""
    verification_note_section = ""
    if session.verification_note is not None:
        note_label = (
            "Agent run failure"
            if session.verification_source == "agent-run"
            else "Verification note"
        )
        verification_note_section = (
            f'<p class="verification-note"><strong>{note_label}:</strong> '
            f"{escape(session.verification_note)}</p>"
        )
    task_verification_section = ""
    if session.verification is not None:
        assessment_type = session.verification.evidence.get(
            "assessment_type"
        )
        verification_title = (
            "AI task assessment"
            if isinstance(assessment_type, str)
            and assessment_type in {"ai_final_state", "ai_trajectory"}
            else "Deterministic final checks"
            if session.verification.evidence.get("verification_type")
            == "browser-use-final-state"
            else "Final checks"
        )
        task_verification_section = _verification_result_section(
            session.verification,
            verification_title,
            summarize_checks=True,
        )
    replay_summary_section = (
        _replay_summary_section(replay_summary)
        if replay_summary is not None
        else ""
    )
    findings_section = _trajectory_findings_section(session)
    auxiliary_events_section = _auxiliary_events_section(session)
    coverage_warning_section = _coverage_warning_section(session)

    document = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Agent action session</title>
    <style>
      :root {{ color-scheme: light; font-family: system-ui, sans-serif; }}
      body {{ background: #f8fafc; color: #0f172a; margin: 0; }}
      main {{ margin: 0 auto; max-width: 1120px; padding: 48px 24px; }}
      header, .action-card, .empty-state {{ background: white; border: 1px solid #e2e8f0;
                                           border-radius: 16px; }}
      header {{ box-shadow: 0 12px 36px rgba(15, 23, 42, .06);
                margin-bottom: 28px; padding: 32px; }}
      h1, h2, h3, p {{ margin-top: 0; }}
      .eyebrow {{ color: #64748b; font-size: 13px; font-weight: 700;
                  letter-spacing: .04em; text-transform: uppercase; }}
      .title-row, .action-heading {{ align-items: center; display: flex;
                                    justify-content: space-between; gap: 16px; }}
      .title-row h1, .action-heading h2 {{ margin-bottom: 0; }}
      .goal {{ font-size: 17px; line-height: 1.55; margin: 20px 0 0; }}
      .result-hero {{ align-items: center; background: #f8fafc; border: 1px solid #e2e8f0;
                      border-left: 6px solid #64748b; border-radius: 12px;
                      display: flex; justify-content: space-between;
                      margin-top: 24px; padding: 22px 24px; }}
      .result-hero-success {{ background: #f0fdf4; border-color: #86efac;
                              border-left-color: #16a34a; }}
      .result-hero-failure {{ background: #fff1f2; border-color: #fda4af;
                              border-left-color: #dc2626; }}
      .result-hero-unverified {{ background: #fffbeb; border-color: #fcd34d;
                                 border-left-color: #d97706; }}
      .result-kicker {{ color: #64748b; display: block; font-size: 12px;
                        font-weight: 800; letter-spacing: .08em;
                        margin-bottom: 5px; text-transform: uppercase; }}
      .result-title {{ display: block; font-size: 30px; letter-spacing: -.02em;
                       line-height: 1.15; }}
      .result-detail {{ color: #475569; margin: 8px 0 0; }}
      .result-mark {{ align-items: center; background: white; border-radius: 50%;
                      color: #166534; display: flex; flex: 0 0 auto;
                      font-size: 24px; font-weight: 900; height: 48px;
                      justify-content: center; width: 48px; }}
      .result-hero-failure .result-mark {{ color: #991b1b; }}
      .result-hero-unverified .result-mark {{ color: #92400e; }}
      .replay-summary {{ border: 2px solid #cbd5e1; border-radius: 12px;
                         margin-top: 18px; padding: 20px; }}
      .replay-summary-reproduced {{ background: #f0fdf4; border-color: #86efac; }}
      .replay-summary-not-reproduced {{ background: #fffbeb; border-color: #fcd34d; }}
      .replay-summary-heading {{ align-items: center; display: flex;
                                 gap: 16px; justify-content: space-between; }}
      .replay-verdict {{ display: block; font-size: 24px; line-height: 1.2; }}
      .replay-verdict-mark {{ align-items: center; background: white;
                              border-radius: 50%; color: #166534; display: flex;
                              flex: 0 0 auto; font-size: 22px; font-weight: 900;
                              height: 44px; justify-content: center; width: 44px; }}
      .replay-summary-not-reproduced .replay-verdict-mark {{ color: #92400e; }}
      .replay-comparison {{ gap: 14px; margin: 18px 0 0; }}
      .replay-comparison dd {{ font-weight: 600; }}
      .replay-divergence {{ border-top: 1px solid #e2e8f0; color: #475569;
                            margin-top: 18px; padding-top: 14px; }}
      .replay-divergence summary {{ cursor: pointer; font-weight: 700; }}
      .replay-divergence p {{ margin: 10px 0 14px; }}
      .replay-divergence-values {{ display: grid; gap: 14px;
                                   grid-template-columns: repeat(2, 1fr); }}
      .replay-divergence-values strong {{ color: #64748b; font-size: 12px;
                                          text-transform: uppercase; }}
      .replay-divergence-values pre {{ margin: 6px 0 0; }}
      .run-stats {{ display: grid; gap: 12px; grid-template-columns: repeat(4, 1fr);
                    margin-top: 16px; }}
      .run-stat {{ background: #f8fafc; border: 1px solid #e2e8f0;
                   border-radius: 10px; padding: 14px 16px; }}
      .run-stat span {{ color: #64748b; display: block; font-size: 12px;
                        font-weight: 700; margin-bottom: 5px; }}
      .run-stat strong {{ font-size: 16px; }}
      .verification-context {{ border-top: 1px solid #e2e8f0; color: #475569;
                               margin-top: 18px; padding-top: 14px; }}
      .verification-context summary {{ cursor: pointer; font-weight: 700; }}
      .verification-context p {{ margin: 10px 0 0; }}
      .verification-note {{ background: #fffbeb; border: 1px solid #fcd34d;
                            border-radius: 8px; color: #78350f;
                            margin: 16px 0 0; padding: 12px 14px; }}
      .failure-summary {{ background: #fff1f2; border: 1px solid #fecdd3;
                          border-radius: 8px; margin-top: 20px; padding: 16px; }}
      .failure-summary h2 {{ font-size: 16px; margin-bottom: 12px; }}
      .failure-summary ul {{ display: flex; flex-wrap: wrap; gap: 10px;
                             list-style: none; margin: 0; padding: 0; }}
      .failure-summary li {{ background: white; border-radius: 999px;
                             display: flex; gap: 8px; padding: 6px 12px; }}
      .coverage-warning {{ background: #fffbeb; border: 2px solid #f59e0b;
                           border-radius: 12px; margin-bottom: 24px;
                           padding: 20px 24px; }}
      .coverage-heading {{ align-items: center; display: flex; gap: 16px;
                           justify-content: space-between; }}
      .coverage-heading h2 {{ margin-bottom: 0; }}
      .coverage-badge {{ background: #fef3c7; border-radius: 999px;
                         color: #92400e; font-size: 12px; font-weight: 800;
                         padding: 6px 10px; white-space: nowrap; }}
      .coverage-warning > p {{ color: #78350f; margin: 12px 0 0; }}
      .coverage-warning .coverage-boundary {{ border-top: 1px solid #fde68a;
                                              color: #92400e; font-size: 14px;
                                              margin-top: 16px; padding-top: 12px; }}
      .trajectory-findings {{ background: #fffbeb; border: 2px solid #f59e0b;
                              border-radius: 12px; margin-bottom: 24px;
                              padding: 24px; }}
      .findings-heading {{ align-items: center; display: flex; gap: 16px;
                           justify-content: space-between; }}
      .findings-heading h2 {{ margin-bottom: 0; }}
      .findings-count, .warning-label {{ background: #fef3c7; border-radius: 999px;
                                        color: #92400e; font-size: 13px;
                                        font-weight: 700; padding: 6px 10px; }}
      .findings-note {{ color: #78350f; margin: 12px 0 20px; }}
      .finding-list {{ display: grid; gap: 12px; }}
      .finding-card {{ background: white; border: 1px solid #fde68a;
                       border-radius: 8px; padding: 18px; }}
      .finding-title-row {{ align-items: center; display: flex; gap: 10px; }}
      .finding-title-row h3 {{ margin-bottom: 0; }}
      .finding-summary {{ font-weight: 600; margin: 14px 0 10px; }}
      .likely-cause {{ background: #fef3c7; border-left: 4px solid #f59e0b;
                       border-radius: 4px; margin: 12px 0; padding: 10px 12px; }}
      .finding-actions {{ color: #475569; margin-bottom: 0; }}
      .finding-actions a {{ color: #1d4ed8; }}
      .finding-details {{ margin-top: 14px; }}
      .finding-details summary {{ cursor: pointer; font-weight: 700; }}
      .finding-details pre {{ margin-bottom: 12px; }}
      .finding-details ul {{ margin-bottom: 0; }}
      .browser-evidence {{ border-top: 1px solid #e2e8f0; margin-top: 20px;
                           padding-top: 16px; }}
      .browser-evidence summary {{ cursor: pointer; font-weight: 700; }}
      .browser-evidence pre {{ margin-bottom: 0; }}
      .auxiliary-events {{ border-top: 1px solid #e2e8f0; color: #475569;
                           margin-top: 18px; padding-top: 14px; }}
      .auxiliary-events summary {{ cursor: pointer; font-weight: 700; }}
      .auxiliary-events p {{ margin: 10px 0; }}
      .auxiliary-events ol {{ margin: 0; padding-left: 24px; }}
      .auxiliary-events li {{ margin: 10px 0; }}
      .auxiliary-events li div {{ align-items: center; display: flex;
                                  gap: 8px; justify-content: space-between; }}
      .auxiliary-events pre {{ margin: 8px 0 0; }}
      .auxiliary-status {{ background: #e2e8f0; border-radius: 999px;
                           color: #475569; font-size: 12px; font-weight: 700;
                           padding: 4px 8px; text-transform: uppercase; }}
      .status {{ border-radius: 999px; font-weight: 700; padding: 6px 12px; }}
      .status-success {{ background: #dcfce7; color: #166534; }}
      .status-failure {{ background: #fee2e2; color: #991b1b; }}
      .status-unverified {{ background: #fef3c7; color: #92400e; }}
      .status-neutral {{ background: #e0f2fe; color: #075985; }}
      .status-empty {{ background: #e2e8f0; color: #475569; }}
      .timeline {{ position: relative; }}
      .timeline::before {{ background: #cbd5e1; bottom: 0; content: "";
                           left: 19px; position: absolute; top: 0; width: 2px; }}
      .timeline-item {{ align-items: flex-start; display: grid; gap: 20px;
                        grid-template-columns: 40px minmax(0, 1fr);
                        margin-bottom: 28px; position: relative; }}
      .marker {{ align-items: center; background: #2563eb; border: 4px solid #f8fafc;
                 border-radius: 50%; color: white; display: flex; font-weight: 700;
                 height: 32px; justify-content: center; width: 32px; z-index: 1; }}
      .action-card {{ box-shadow: 0 6px 20px rgba(15, 23, 42, .04); padding: 24px; }}
      .action-evidence {{ border-top: 1px solid #e2e8f0; margin-top: 22px;
                          padding-top: 20px; }}
      .action-evidence-heading {{ align-items: flex-start; display: flex;
                                  gap: 16px; justify-content: space-between; }}
      .action-evidence-heading h3 {{ margin-bottom: 0; }}
      .section-note {{ color: #64748b; font-size: 14px; margin: 6px 0 0; }}
      .evidence-flow {{ background: #eff6ff; border-radius: 999px; color: #1d4ed8;
                        font-size: 12px; font-weight: 800; padding: 6px 10px;
                        white-space: nowrap; }}
      .action-screenshots {{ margin-top: 16px; }}
      .action-screenshots figure {{ background: #f8fafc; border: 1px solid #e2e8f0;
                                    border-radius: 10px; padding: 10px; }}
      .action-screenshots figure img {{ max-height: 440px; object-fit: contain; }}
      .action-technical {{ border-top: 1px solid #e2e8f0; color: #334155;
                           margin-top: 22px; padding-top: 16px; }}
      .action-technical > summary {{ color: #0f172a; cursor: pointer;
                                     font-weight: 800; }}
      .action-technical-content {{ margin-top: 16px; }}
      .action-technical-content > .technical-details {{ margin-top: 12px; }}
      .technical-group {{ margin: 0 0 20px; }}
      .technical-group h3 {{ margin-bottom: 0; }}
      .technical-group pre {{ margin: 12px 0 0; }}
      dl {{ display: grid; gap: 20px; grid-template-columns: repeat(2, 1fr); }}
      dt {{ color: #64748b; font-size: 13px; font-weight: 700; }}
      dd {{ margin: 6px 0 0; overflow-wrap: anywhere; }}
      pre {{ background: #0f172a; border-radius: 8px; color: #e2e8f0;
             overflow-x: auto; padding: 16px; }}
      .failure {{ background: #fff1f2; border: 1px solid #fecdd3;
                  border-radius: 8px; margin-top: 20px; padding: 16px; }}
      .failure p {{ margin: 8px 0 0; white-space: pre-wrap; }}
      .key-value-grid {{ background: rgba(255, 255, 255, .72);
                         border-radius: 8px; grid-template-columns:
                         repeat(auto-fit, minmax(140px, 1fr)); margin: 0;
                         padding: 16px; }}
      .raw-error {{ margin-top: 16px; }}
      .raw-error summary {{ cursor: pointer; font-weight: 700; }}
      .raw-error pre {{ margin-bottom: 0; }}
      .technical-details {{ margin-top: 14px; }}
      .technical-details summary {{ cursor: pointer; font-weight: 700; }}
      .technical-details pre {{ margin: 10px 0 0; }}
      .verification {{ background: white; border: 1px solid #cbd5e1;
                       border-radius: 12px; margin: 0 0 28px; padding: 22px; }}
      .action-card .verification {{ margin: 20px 0 0; }}
      .verification-heading {{ align-items: center; display: flex;
                               justify-content: space-between; }}
      .verification-heading h2 {{ margin-bottom: 0; }}
      .check-total {{ border-radius: 999px; font-size: 12px; font-weight: 800;
                      padding: 6px 10px; text-transform: uppercase; }}
      .check-total-passed {{ background: #dcfce7; color: #166534; }}
      .check-total-failed {{ background: #fee2e2; color: #991b1b; }}
      .verification-failure {{ background: #fff1f2; border-radius: 8px;
                               margin-top: 16px; padding: 16px; }}
      .verification-failure p {{ margin-bottom: 0; white-space: pre-wrap; }}
      .verification-check-list {{ margin-top: 20px; }}
      .assessment-summary {{ color: #334155; margin: 14px 0 0; }}
      .assessment-summary summary {{ cursor: pointer; font-weight: 700; }}
      .assessment-summary p {{ font-size: 16px; line-height: 1.55;
                               margin: 10px 0 0; }}
      .assessment-evidence {{ margin-top: 18px; }}
      .assessment-evidence ul {{ color: #334155; line-height: 1.55;
                                 margin-bottom: 0; padding-left: 22px; }}
      .verification-check-list ol {{ display: grid; gap: 10px;
                                     list-style: none; margin: 0; padding: 0; }}
      .verification-check {{ border: 1px solid #e2e8f0; border-left-width: 4px;
                             border-radius: 8px; padding: 14px; }}
      .verification-check-passed {{ border-left-color: #22c55e; }}
      .verification-check-failed {{ border-left-color: #ef4444; }}
      .verification-check div {{ align-items: center; display: flex;
                                 justify-content: space-between; }}
      .verification-check p {{ margin: 8px 0 4px; }}
      .verification-check small {{ color: #64748b; }}
      .check-status {{ font-size: 12px; font-weight: 700;
                       text-transform: uppercase; }}
      .verification-check-passed .check-status {{ color: #166534; }}
      .verification-check-failed .check-status {{ color: #991b1b; }}
      .verification-evidence {{ margin-top: 16px; }}
      .verification-evidence summary {{ cursor: pointer; font-weight: 700; }}
      .verification-evidence pre {{ margin-bottom: 0; }}
      .action-screenshots {{ display: grid; gap: 16px;
                             grid-template-columns: repeat(2, minmax(0, 1fr));
                             margin-top: 20px; }}
      figure {{ margin: 0; }}
      figcaption {{ color: #64748b; font-size: 13px; font-weight: 700;
                    margin-bottom: 8px; }}
      figure img {{ border: 1px solid #e2e8f0; border-radius: 8px;
                    display: block; height: auto; width: 100%; }}
      .missing {{ color: #64748b; }}
      .empty-state {{ padding: 32px; text-align: center; }}
      @media (max-width: 800px) {{
        dl, .action-screenshots, .replay-comparison, .replay-divergence-values,
        .run-stats {{
          grid-template-columns: 1fr;
        }}
        .title-row, .action-heading, .findings-heading, .coverage-heading {{
          align-items: flex-start; flex-direction: column; }}
        .result-mark {{ display: none; }}
      }}
    </style>
  </head>
  <body>
    <main>
      <header>
        <p class="eyebrow">Agent DevTools · Session schema {SESSION_SCHEMA_VERSION}</p>
        <div class="title-row">
          <h1>{report_title}</h1>
        </div>
        {goal_section}
        <section class="result-hero result-hero-{overall_status}">
          <div>
            <span class="result-kicker">Final result</span>
            <strong class="result-title">{escape(result_title)}</strong>
            <p class="result-detail">{escape(result_detail)}</p>
          </div>
          <span class="result-mark" aria-hidden="true">{result_mark}</span>
        </section>
{replay_summary_section}
        <section class="run-stats" aria-label="Run summary">
          <div class="run-stat"><span>Actions</span><strong>{session.action_count}</strong></div>
          <div class="run-stat"><span>Executed</span><strong>{execution_success_count} succeeded</strong></div>
          <div class="run-stat"><span>Action failures</span><strong>{failure_count}</strong></div>
          <div class="run-stat"><span>Action checks</span><strong>{step_check_value}</strong></div>
        </section>
{failure_summary}
{verification_note_section}
{inferred_goal_section}
{automatic_verification_section}
{auxiliary_events_section}
      </header>
{coverage_warning_section}
{findings_section}
{task_verification_section}
      <div class="timeline">
{cards}
      </div>
    </main>
  </body>
</html>
"""

    _write_utf8_text(output_path, document)


def _write_utf8_text(output_path: Path, document: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = "\n".join(line.rstrip() for line in document.splitlines()) + "\n"
    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        output_file.write(document)
