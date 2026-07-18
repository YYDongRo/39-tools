import json
from html import escape
from pathlib import Path

from agent_devtools.action import ActionRecord
from agent_devtools.serialization import action_to_dict


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


def write_action_html(action: ActionRecord, output_path: Path) -> None:
    data = action_to_dict(action)
    status = escape(str(data["status"]))
    arguments = escape(
        json.dumps(data["arguments"], ensure_ascii=False, indent=2)
    )
    failure_reason = data["failure_reason"]
    failure_section = ""
    if failure_reason is not None:
        failure_section = f"""
      <section class="failure">
        <h2>Failure reason</h2>
        <p>{escape(str(failure_reason))}</p>
      </section>"""

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
      dl {{ display: grid; gap: 20px; grid-template-columns: repeat(4, 1fr); }}
      dt {{ color: #64748b; font-size: 13px; font-weight: 700; }}
      dd {{ margin: 6px 0 0; overflow-wrap: anywhere; }}
      pre {{ background: #0f172a; border-radius: 8px; color: #e2e8f0;
             overflow-x: auto; padding: 16px; }}
      .failure {{ background: #fff1f2; border: 1px solid #fecdd3; }}
      .failure p {{ white-space: pre-wrap; }}
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
          <span class="status status-{status}">{status}</span>
        </div>
      </header>
      <section>
        <h2>Action details</h2>
        <dl>
          <div><dt>Start time</dt><dd>{escape(str(data["start_time"]))}</dd></div>
          <div><dt>Duration</dt><dd>{data["duration_ms"]} ms</dd></div>
          <div><dt>Before screenshot</dt><dd>{escape(str(data["screenshot_before"] or "—"))}</dd></div>
          <div><dt>After screenshot</dt><dd>{escape(str(data["screenshot_after"] or "—"))}</dd></div>
        </dl>
      </section>
      <section>
        <h2>Arguments</h2>
        <pre>{arguments}</pre>
      </section>{failure_section}
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
