"""Self-contained static HTML report - the same evidence as the JSON report.

``write_html(report, path)`` takes a payload produced by :func:`clinic.report.write_reports`
(i.e. the contents of ``reports/<name>-<ts>.json``) and renders one standalone file:
no external CSS, JS, fonts or images, so the report can be mailed, attached to an issue
or opened straight off disk.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

#: Status pill colours: text, background, border.
_PILL = {
    "PASS": ("#0f5132", "#d7f3e3", "#a9e0c4"),
    "FIXED": ("#1c3f94", "#dce6ff", "#b6c8f7"),
    "FAIL": ("#8a1c24", "#fbdcde", "#f3b7bc"),
    "INFRA_ERROR": ("#4a4a55", "#e6e6ea", "#d0d0d8"),
}

#: The overall verdict banner. ENV_SPECIFIC is amber: a real finding, but about the host.
_VERDICT = {
    "HEALTHY": ("#0f5132", "#d7f3e3", "#a9e0c4"),
    "FIXABLE": ("#1c3f94", "#dce6ff", "#b6c8f7"),
    "ENV_SPECIFIC": ("#7a4a06", "#fdeccd", "#f2d49a"),
    "BROKEN": ("#8a1c24", "#fbdcde", "#f3b7bc"),
}

_CSS = """
:root {
  --bg: #f6f6f8;
  --card: #ffffff;
  --ink: #1b1b1f;
  --muted: #62626d;
  --line: #e3e3e8;
  --accent: #4f46e5;
  --code-bg: #f3f3f6;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 32px 16px 64px;
  background: var(--bg);
  color: var(--ink);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.wrap { max-width: 1040px; margin: 0 auto; }
header.card { border-top: 3px solid var(--accent); }
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 20px 22px;
  margin-bottom: 20px;
}
h1 { font-size: 22px; margin: 0 0 4px; letter-spacing: -0.01em; }
h1 .name { font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace; color: var(--accent); }
h2 { font-size: 15px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin: 0 0 12px; }
.sub { color: var(--muted); font-size: 13px; margin: 0 0 14px; }
.sub code { background: var(--code-bg); padding: 1px 5px; border-radius: 4px; }
.verdict {
  display: inline-block; padding: 6px 14px; border-radius: 999px;
  font-weight: 700; font-size: 14px; letter-spacing: .04em; border: 1px solid;
}
.counts { list-style: none; display: flex; flex-wrap: wrap; gap: 10px; padding: 0; margin: 16px 0 0; }
.counts li {
  background: var(--code-bg); border: 1px solid var(--line); border-radius: 8px;
  padding: 8px 14px; min-width: 86px;
}
.counts .n { display: block; font-size: 20px; font-weight: 700; line-height: 1.2; }
.counts .k { font-size: 11px; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font-size: 11px; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); }
td.num, th.num { text-align: right; width: 42px; color: var(--muted); }
code, pre, .mono { font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace; }
td code { font-size: 12.5px; word-break: break-all; }
.pill {
  display: inline-block; padding: 2px 9px; border-radius: 999px; border: 1px solid;
  font-size: 11.5px; font-weight: 700; letter-spacing: .03em;
}
.cat { font-size: 12.5px; }
.cat .arrow { color: var(--accent); font-weight: 700; }
.muted { color: var(--muted); }
details { border: 1px solid var(--line); border-radius: 8px; margin-top: 10px; background: var(--card); }
details[open] { border-color: #c9c6f2; }
summary {
  cursor: pointer; padding: 10px 14px; font-size: 13.5px; font-weight: 600;
  display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
}
summary::marker { color: var(--accent); }
.detail-body { padding: 0 14px 14px; }
.detail-body p { margin: 8px 0; font-size: 13.5px; }
.label { font-size: 11px; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); display: block; margin-top: 12px; }
pre {
  background: var(--code-bg); border: 1px solid var(--line); border-radius: 6px;
  padding: 11px 13px; overflow-x: auto; font-size: 12.5px; margin: 6px 0 0;
  white-space: pre-wrap; word-break: break-word;
}
pre.fix { background: #f0efff; border-color: #d4d1f7; }
footer { color: var(--muted); font-size: 12px; text-align: center; }
"""


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _pill(status: str) -> str:
    fg, bg, border = _PILL.get(status, ("#4a4a55", "#e6e6ea", "#d0d0d8"))
    return (f'<span class="pill" style="color:{fg};background:{bg};border-color:{border}">'
            f"{_esc(status)}</span>")


def _category_cell(step: dict) -> str:
    """`missing_tool` - or `missing_tool → example_snippet` once a fix was re-classified."""
    category = step.get("category")
    if not category:
        return '<span class="muted">-</span>'
    after = (step.get("after_fix") or {}).get("category")
    if after:
        return (f'<span class="cat">{_esc(category)} '
                f'<span class="arrow">&rarr;</span> {_esc(after)}</span>')
    return f'<span class="cat">{_esc(category)}</span>'


def _judge_summary(steps: list[dict]) -> str:
    """The judge backends that actually ran, counted from the rows."""
    used: dict[str, int] = {}
    for step in steps:
        judge = step.get("judge")
        if judge:
            used[judge] = used.get(judge, 0) + 1
    if not used:
        return "none (no step needed diagnosing)"
    return ", ".join(f"{name} x{n}" for name, n in sorted(used.items(), key=lambda kv: -kv[1]))


def _header(report: dict) -> str:
    verdict = str(report.get("verdict", "UNKNOWN"))
    fg, bg, border = _VERDICT.get(verdict, ("#4a4a55", "#e6e6ea", "#d0d0d8"))
    counts = report.get("counts") or {}
    steps = report.get("steps") or []

    tiles = []
    for key in ("PASS", "FIXED", "FAIL", "INFRA_ERROR"):
        if key in counts and (counts[key] or key in ("PASS", "FIXED", "FAIL")):
            tiles.append(f'<li><span class="n">{_esc(counts[key])}</span>'
                         f'<span class="k">{_esc(key.replace("_", " "))}</span></li>')
    tiles.append(f'<li><span class="n">{len(steps)}</span><span class="k">steps</span></li>')

    meta = [f'Source: <code>{_esc(report.get("skill_file", "-"))}</code>']
    if report.get("generated_at"):
        meta.append(f'Generated: {_esc(report["generated_at"])}')
    meta.append("Fix mode: " + ("on" if report.get("fix_mode") else "off"))
    model = report.get("llm_model")
    meta.append("Judge: " + (f"nosana LLM ({_esc(model)})" if report.get("llm_judge")
                             else "rules (deterministic)"))
    meta.append(f"Backends used: {_esc(_judge_summary(steps))}")

    return (
        '<header class="card">'
        f'<h1>Skill Clinic &mdash; <span class="name">{_esc(report.get("skill", "?"))}</span></h1>'
        f'<p class="sub">{" &middot; ".join(meta)}</p>'
        f'<span class="verdict" style="color:{fg};background:{bg};border-color:{border}">'
        f"VERDICT: {_esc(verdict)}</span>"
        f'<ul class="counts">{"".join(tiles)}</ul>'
        "</header>"
    )


def _table(steps: list[dict]) -> str:
    rows = []
    for step in steps:
        rows.append(
            "<tr>"
            f'<td class="num">{_esc(step.get("index"))}</td>'
            f'<td>{_esc(step.get("title"))}</td>'
            f'<td><code>{_esc(step.get("command"))}</code></td>'
            f'<td>{_pill(str(step.get("status", "")))}</td>'
            f"<td>{_category_cell(step)}</td>"
            f'<td class="num">{_esc(step.get("seconds"))}</td>'
            f'<td class="muted">{_esc(step.get("judge") or "-")}</td>'
            "</tr>"
        )
    return (
        '<section class="card"><h2>Steps</h2><table>'
        '<thead><tr><th class="num">#</th><th>Step</th><th>Command</th><th>Status</th>'
        '<th>Category</th><th class="num">Sec</th><th>Judge</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></section>'
    )


def _details(steps: list[dict]) -> str:
    blocks = []
    for step in steps:
        body = [f'<span class="label">command</span><pre>{_esc(step.get("command"))}</pre>']
        body.append(f'<p class="muted">exit code <code>{_esc(step.get("exit_code"))}</code>'
                    f' &middot; {_esc(step.get("seconds"))}s'
                    + (f' &middot; confidence {_esc(step.get("confidence"))}'
                       if step.get("confidence") is not None else "")
                    + "</p>")
        if step.get("explanation"):
            body.append(f'<p><strong>Diagnosis:</strong> {_esc(step["explanation"])}</p>')
        after = step.get("after_fix") or {}
        if after:
            body.append(
                f'<p><strong>After the fix ran:</strong> still failing, now classified as '
                f'<code>{_esc(after.get("category"))}</code>'
                + (f' &mdash; {_esc(after.get("explanation"))}' if after.get("explanation") else "")
                + "</p>")
        if step.get("fix_command"):
            body.append('<span class="label">proposed fix</span>'
                        f'<pre class="fix">{_esc(step["fix_command"])}</pre>')
        else:
            body.append('<p class="muted">No fix proposed.</p>')
        body.append('<span class="label">output tail</span>'
                    f'<pre>{_esc((step.get("output") or "")[-2000:]) or "(no output)"}</pre>')

        blocks.append(
            "<details>"
            f'<summary>{_pill(str(step.get("status", "")))} '
            f'<span>{_esc(step.get("index"))}. {_esc(step.get("title"))}</span> '
            f"{_category_cell(step)}</summary>"
            f'<div class="detail-body">{"".join(body)}</div>'
            "</details>"
        )
    return f'<section class="card"><h2>Evidence</h2>{"".join(blocks)}</section>'


def render_html(report: dict) -> str:
    """Render a JSON report payload into one self-contained HTML document."""
    steps = report.get("steps") or []
    title = f'Skill Clinic - {report.get("skill", "report")} ({report.get("verdict", "")})'
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_esc(title)}</title>"
        f"<style>{_CSS}</style></head><body><div class=\"wrap\">"
        + _header(report)
        + _table(steps)
        + _details(steps)
        + "<footer>Generated by Skill Clinic &middot; every status comes from a real exit code "
          "in a fresh sandbox.</footer>"
        "</div></body></html>\n"
    )


def write_html(report: dict, path: Path) -> Path:
    """Write the HTML report for ``report`` to ``path`` and return that path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(report), encoding="utf-8")
    return path


def write_html_from_json(json_path: Path) -> Path:
    """Regenerate ``<name>.html`` beside an existing ``<name>.json`` report."""
    json_path = Path(json_path)
    report = json.loads(json_path.read_text(encoding="utf-8"))
    return write_html(report, json_path.with_suffix(".html"))
