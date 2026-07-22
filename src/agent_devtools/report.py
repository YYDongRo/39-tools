import json
from html import escape
from pathlib import Path

from agent_devtools.action import ActionOutcome, ActionRecord, ActionStatus
from agent_devtools.failure import FailureCategory
from agent_devtools.serialization import SESSION_SCHEMA_VERSION, action_to_dict
from agent_devtools.session import ActionSession
from agent_devtools.verification import VerificationResult


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
        return "not run"
    return "passed" if action.verification.passed else "failed"


def _verification_result_section(
    verification: VerificationResult,
    title: str,
) -> str:
    status = "passed" if verification.passed else "failed"
    evidence_section = ""
    if verification.evidence:
        evidence = escape(
            json.dumps(verification.evidence, ensure_ascii=False, indent=2)
        )
        evidence_section = f"<h3>Verification evidence</h3><pre>{evidence}</pre>"

    failure_section = ""
    if verification.failure_reason is not None:
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

    return f"""
      <section class="verification">
        <h2>{escape(title)}</h2>
        <dl>
          <div><dt>Status</dt><dd>{status}</dd></div>
          <div><dt>Expected state</dt><dd>{escape(verification.expected_state)}</dd></div>
          <div><dt>Observed state</dt><dd>{escape(verification.observed_state)}</dd></div>
        </dl>
        {failure_section}
        {evidence_section}
      </section>"""


def _verification_section(action: ActionRecord) -> str:
    verification = action.verification
    if verification is None:
        return ""
    return _verification_result_section(verification, "Verification")


def _outcome_failure_category(action: ActionRecord) -> FailureCategory | None:
    if action.status is ActionStatus.FAILURE:
        return action.failure_category
    if action.verification is not None and not action.verification.passed:
        return action.verification.failure_category
    return None


def write_action_html(action: ActionRecord, output_path: Path) -> None:
    data = action_to_dict(action)
    execution_status = escape(str(data["status"]))
    outcome = escape(action.outcome.value)
    verification_status = _verification_label(action)
    arguments = escape(
        json.dumps(data["arguments"], ensure_ascii=False, indent=2)
    )
    failure_reason = data["failure_reason"]
    failure_category = data["failure_category"]
    failure_evidence = data["failure_evidence"]
    failure_section = ""
    if failure_reason is not None:
        category_section = ""
        if failure_category is not None:
            category_section = (
                "<p><strong>Category:</strong> "
                f"{escape(str(failure_category))}</p>"
            )
        evidence_section = ""
        if failure_evidence:
            evidence = escape(
                json.dumps(failure_evidence, ensure_ascii=False, indent=2)
            )
            evidence_section = f"<h3>Diagnostic evidence</h3><pre>{evidence}</pre>"
        failure_section = f"""
      <section class="failure">
        <h2>Failure reason</h2>
        {category_section}
        <p>{escape(str(failure_reason))}</p>
        {evidence_section}
      </section>"""
    verification_section = _verification_section(action)

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
      dl {{ display: grid; gap: 20px; grid-template-columns: repeat(4, 1fr); }}
      dt {{ color: #64748b; font-size: 13px; font-weight: 700; }}
      dd {{ margin: 6px 0 0; overflow-wrap: anywhere; }}
      pre {{ background: #0f172a; border-radius: 8px; color: #e2e8f0;
             overflow-x: auto; padding: 16px; }}
      .failure {{ background: #fff1f2; border: 1px solid #fecdd3; }}
      .failure p {{ white-space: pre-wrap; }}
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
          <span class="status status-{outcome}">{outcome}</span>
        </div>
      </header>
      <section>
        <h2>Action details</h2>
        <dl>
          <div><dt>Final outcome</dt><dd>{outcome}</dd></div>
          <div><dt>Execution status</dt><dd>{execution_status}</dd></div>
          <div><dt>Verification status</dt><dd>{verification_status}</dd></div>
          <div><dt>Start time</dt><dd>{escape(str(data["start_time"]))}</dd></div>
          <div><dt>Duration</dt><dd>{data["duration_ms"]} ms</dd></div>
          <div><dt>Before screenshot</dt><dd>{escape(str(data["screenshot_before"] or "—"))}</dd></div>
          <div><dt>After screenshot</dt><dd>{escape(str(data["screenshot_after"] or "—"))}</dd></div>
        </dl>
      </section>
      <section>
        <h2>Arguments</h2>
        <pre>{arguments}</pre>
      </section>{failure_section}{verification_section}
      <section class="screenshots">
{_screenshot_panel("Before", data["screenshot_before"])}
{_screenshot_panel("After", data["screenshot_after"])}
      </section>
    </main>
  </body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")


def _session_action_card(index: int, action: ActionRecord) -> str:
    data = action_to_dict(action)
    execution_status = escape(str(data["status"]))
    outcome = escape(action.outcome.value)
    verification_status = _verification_label(action)
    arguments = escape(
        json.dumps(data["arguments"], ensure_ascii=False, indent=2)
    )
    failure_reason = data["failure_reason"]
    failure_category = data["failure_category"]
    failure_evidence = data["failure_evidence"]
    failure_section = ""
    if failure_reason is not None:
        category_section = ""
        if failure_category is not None:
            category_section = (
                "<p><strong>Category:</strong> "
                f"{escape(str(failure_category))}</p>"
            )
        evidence_section = ""
        if failure_evidence:
            evidence = escape(
                json.dumps(failure_evidence, ensure_ascii=False, indent=2)
            )
            evidence_section = f"<h3>Diagnostic evidence</h3><pre>{evidence}</pre>"
        failure_section = f"""
            <div class="failure">
              <strong>Failure reason</strong>
              {category_section}
              <p>{escape(str(failure_reason))}</p>
              {evidence_section}
            </div>"""
    verification_section = _verification_section(action)

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
        <article class="timeline-item">
          <div class="marker">{index}</div>
          <div class="action-card">
            <div class="action-heading">
              <div>
                <p class="eyebrow">Action {index}</p>
                <h2>{escape(str(data["action_type"]))}</h2>
              </div>
              <span class="status status-{outcome}">{outcome}</span>
            </div>
            <dl>
              <div><dt>Execution status</dt><dd>{execution_status}</dd></div>
              <div><dt>Verification status</dt><dd>{verification_status}</dd></div>
              <div><dt>Start time</dt><dd>{escape(str(data["start_time"]))}</dd></div>
              <div><dt>Duration</dt><dd>{data["duration_ms"]} ms</dd></div>
            </dl>
            <h3>Arguments</h3>
            <pre>{arguments}</pre>{failure_section}{verification_section}
            <div class="action-screenshots">{screenshot_section}
            </div>
          </div>
        </article>"""


def write_session_html(session: ActionSession, output_path: Path) -> None:
    failure_count = sum(
        action.outcome is ActionOutcome.FAILURE for action in session.actions
    )
    success_count = sum(
        action.outcome is ActionOutcome.SUCCESS for action in session.actions
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
        overall_label = (
            "task successful"
            if session.outcome is ActionOutcome.SUCCESS
            else "task failed"
        )
    elif session.goal is not None:
        overall_status = "unverified"
        overall_label = "task unverified"
    elif session.action_count == 0:
        overall_status = "empty"
        overall_label = "empty"
    elif session.has_failures:
        overall_status = "failure"
        overall_label = "contains failures"
    elif unverified_count:
        overall_status = "unverified"
        overall_label = "contains unverified actions"
    else:
        overall_status = "success"
        overall_label = "all successful"

    action_label = "action" if session.action_count == 1 else "actions"
    success_label = (
        "verified success" if success_count == 1 else "verified successes"
    )
    failure_label = "failure" if failure_count == 1 else "failures"
    unverified_label = (
        "unverified action" if unverified_count == 1 else "unverified actions"
    )
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
            '<p class="goal"><strong>Goal:</strong> '
            f"{escape(session.goal)}</p>"
        )
    task_verification_section = ""
    if session.verification is not None:
        task_verification_section = _verification_result_section(
            session.verification,
            "Task verification",
        )

    document = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Agent action session</title>
    <style>
      :root {{ color-scheme: light; font-family: system-ui, sans-serif; }}
      body {{ background: #f3f4f6; color: #0f172a; margin: 0; }}
      main {{ margin: 0 auto; max-width: 1200px; padding: 40px 24px; }}
      header, .action-card, .empty-state {{ background: white; border-radius: 12px; }}
      header {{ margin-bottom: 32px; padding: 28px; }}
      h1, h2, h3, p {{ margin-top: 0; }}
      .eyebrow {{ color: #64748b; font-size: 13px; font-weight: 700;
                  letter-spacing: .04em; text-transform: uppercase; }}
      .title-row, .action-heading {{ align-items: center; display: flex;
                                    justify-content: space-between; gap: 16px; }}
      .title-row h1, .action-heading h2 {{ margin-bottom: 0; }}
      .goal {{ font-size: 18px; margin: 20px 0 0; }}
      .summary {{ color: #475569; margin: 16px 0 0; }}
      .failure-summary {{ background: #fff1f2; border: 1px solid #fecdd3;
                          border-radius: 8px; margin-top: 20px; padding: 16px; }}
      .failure-summary h2 {{ font-size: 16px; margin-bottom: 12px; }}
      .failure-summary ul {{ display: flex; flex-wrap: wrap; gap: 10px;
                             list-style: none; margin: 0; padding: 0; }}
      .failure-summary li {{ background: white; border-radius: 999px;
                             display: flex; gap: 8px; padding: 6px 12px; }}
      .status {{ border-radius: 999px; font-weight: 700; padding: 6px 12px; }}
      .status-success {{ background: #dcfce7; color: #166534; }}
      .status-failure {{ background: #fee2e2; color: #991b1b; }}
      .status-unverified {{ background: #fef3c7; color: #92400e; }}
      .status-empty {{ background: #e2e8f0; color: #475569; }}
      .timeline {{ position: relative; }}
      .timeline::before {{ background: #cbd5e1; bottom: 0; content: "";
                           left: 19px; position: absolute; top: 0; width: 2px; }}
      .timeline-item {{ align-items: flex-start; display: grid; gap: 20px;
                        grid-template-columns: 40px minmax(0, 1fr);
                        margin-bottom: 28px; position: relative; }}
      .marker {{ align-items: center; background: #2563eb; border: 4px solid #f3f4f6;
                 border-radius: 50%; color: white; display: flex; font-weight: 700;
                 height: 32px; justify-content: center; width: 32px; z-index: 1; }}
      .action-card {{ padding: 24px; }}
      dl {{ display: grid; gap: 20px; grid-template-columns: repeat(2, 1fr); }}
      dt {{ color: #64748b; font-size: 13px; font-weight: 700; }}
      dd {{ margin: 6px 0 0; overflow-wrap: anywhere; }}
      pre {{ background: #0f172a; border-radius: 8px; color: #e2e8f0;
             overflow-x: auto; padding: 16px; }}
      .failure {{ background: #fff1f2; border: 1px solid #fecdd3;
                  border-radius: 8px; margin-top: 20px; padding: 16px; }}
      .failure p {{ margin: 8px 0 0; white-space: pre-wrap; }}
      .verification {{ border: 1px solid #cbd5e1; border-radius: 8px;
                       margin-top: 20px; padding: 16px; }}
      .verification-failure {{ background: #fff1f2; border-radius: 8px;
                               margin-top: 16px; padding: 16px; }}
      .verification-failure p {{ margin-bottom: 0; white-space: pre-wrap; }}
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
        dl, .action-screenshots {{ grid-template-columns: 1fr; }}
        .title-row, .action-heading {{ align-items: flex-start; flex-direction: column; }}
      }}
    </style>
  </head>
  <body>
    <main>
      <header>
        <p class="eyebrow">Agent DevTools · Session schema {SESSION_SCHEMA_VERSION}</p>
        <div class="title-row">
          <h1>Action session</h1>
          <span class="status status-{overall_status}">{overall_label}</span>
        </div>
        {goal_section}
        <p class="summary">{session.action_count} {action_label} · {success_count} {success_label} · {failure_count} {failure_label} · {unverified_count} {unverified_label}</p>
{failure_summary}
      </header>
{task_verification_section}
      <div class="timeline">
{cards}
      </div>
    </main>
  </body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
