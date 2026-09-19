"""Terminal table + markdown/json evidence report."""

from __future__ import annotations

import json
import os
import re
import time

from rich.console import Console
from rich.table import Table

ENV_CATEGORIES = {"missing_secret", "env_specific", "network_blocked"}

#: Steps whose sandbox call itself failed (SDK/network). They say nothing about the
#: skill, are never sent to the judge, and never move the verdict.
INFRA_STATUS = "INFRA_ERROR"

_STATUS_STYLE = {
    "PASS": "bold green",
    "FIXED": "bold cyan",
    "FAIL": "bold red",
    INFRA_STATUS: "bold magenta",
}


def count_infra_errors(results) -> int:
    """How many steps failed because of our infrastructure, not the skill."""
    return sum(1 for r in results if r.status == INFRA_STATUS)


def decide_verdict(results) -> str:
    """Exit codes decide everything here - the model never votes.

    ``INFRA_ERROR`` steps are excluded entirely: a Daytona SDK or network failure on
    our side is not evidence about the skill, so it is reported separately instead.
    """
    results = [r for r in results if r.status != INFRA_STATUS]
    failures = [r for r in results if r.status in ("FAIL", "FIXED")]
    if not failures:
        return "HEALTHY"
    unresolved = [r for r in failures if r.status != "FIXED"]
    if not unresolved:
        return "FIXABLE"
    if all((r.category in ENV_CATEGORIES) for r in unresolved):
        return "ENV_SPECIFIC"
    return "BROKEN"


def _heading(r) -> str:
    """`3. Install` - but never `3. 3. Install` when the heading was already numbered."""
    title = (r.title or "").strip()
    if re.match(r"^\d+[.)]\s", title):
        return title
    return f"{r.index}. {title}"


def category_cell(r, arrow: str = "->") -> str:
    """`missing_tool` - or `missing_tool -> example_snippet` when a failed fix was re-read.

    ``after_fix`` is the rules classifier's reading of the output the *fix attempt*
    produced. It is evidence only: the row stays FAIL and the verdict never moves.
    """
    category = getattr(r, "category", None) or (r.get("category") if isinstance(r, dict) else None)
    if not category:
        return "-"
    after_fix = getattr(r, "after_fix", None) if not isinstance(r, dict) else r.get("after_fix")
    after = (after_fix or {}).get("category")
    return f"{category} {arrow} {after}" if after else str(category)


def _truncate(text: str, width: int = 60) -> str:
    one_line = " ; ".join(text.splitlines())
    return one_line if len(one_line) <= width else one_line[: width - 1] + "…"


def render_table(console: Console, skill_name: str, results) -> None:
    table = Table(title=f"Skill Clinic - {skill_name}", header_style="bold magenta")
    table.add_column("#", justify="right", width=3)
    table.add_column("Step", max_width=26, overflow="ellipsis")
    table.add_column("Command", max_width=60, overflow="ellipsis")
    table.add_column("Status", width=6)
    table.add_column("Category", width=30, overflow="fold")
    table.add_column("Sec", justify="right", width=5)
    table.add_column("Judge", width=12, overflow="ellipsis")
    for r in results:
        table.add_row(
            str(r.index), r.title, _truncate(r.command, 60),
            f"[{_STATUS_STYLE.get(r.status, '')}]{r.status}[/]",
            category_cell(r, "\u2192"), f"{r.seconds:.1f}", r.judge or "-",
        )
    console.print(table)


def _security_section(results) -> list[str]:
    """Markdown 'Security observations' - what each flagged step actually tried to do."""
    flagged = [r for r in results if getattr(r, "security", None)]
    if not flagged:
        return ["", "## Security observations", "",
                "No injected or suspicious behaviour was observed in any step."]
    lines = ["", "## Security observations", "",
             "Every step below was **executed** in a throwaway Daytona sandbox with "
             "arbitrary egress blocked, so this is what the skill *tried* to do, not a "
             "static guess. Findings are observations only - they do not change the verdict.",
             "",
             "| # | Step | Severity | Rule | Evidence |",
             "|---|------|----------|------|----------|"]
    for r in flagged:
        for f in r.security:
            evidence = f["evidence"].replace("|", "\\|")
            lines.append(f"| {r.index} | {r.title} | {f['severity']} | {f['rule']} | "
                         f"`{evidence}` |")
    lines.append("")
    for r in flagged:
        lines.append(f"- **step {r.index} ({r.title})**: "
                     + "; ".join(f"{f['rule']} - {f['note']}" for f in r.security))
    return lines


def write_reports(skill_name: str, skill_file: str, results, verdict: str,
                  out_dir: str = "reports", meta: dict | None = None) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = os.path.join(out_dir, f"{skill_name}-{stamp}")
    meta = meta or {}

    payload = {
        "skill": skill_name,
        "skill_file": skill_file,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "verdict": verdict,
        "counts": {s: sum(1 for r in results if r.status == s)
                   for s in ("PASS", "FAIL", "FIXED", INFRA_STATUS)},
        **meta,
        "steps": [r.to_dict() for r in results],
    }
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)

    lines = [
        f"# Skill Clinic report - `{skill_name}`",
        "",
        f"- Source: `{skill_file}`",
        f"- Generated: {payload['generated_at']}",
        f"- **Verdict: {verdict}**",
        f"- Steps: {len(results)} "
        f"(PASS {payload['counts']['PASS']}, FIXED {payload['counts']['FIXED']}, "
        f"FAIL {payload['counts']['FAIL']}, "
        f"infrastructure errors {payload['counts'][INFRA_STATUS]})",
        "",
        "| # | Step | Command | Status | Category | Sec | Judge |",
        "|---|------|---------|--------|----------|-----|-------|",
    ]
    for r in results:
        cmd = _truncate(r.command, 60).replace("|", "\\|")
        lines.append(
            f"| {r.index} | {r.title} | `{cmd}` | {r.status} | "
            f"{category_cell(r, '→')} | {r.seconds:.1f} | {r.judge or '-'} |"
        )
    lines += _security_section(results)
    lines.append("")
    lines.append("## Evidence")
    for r in results:
        lines += ["", f"### {_heading(r)} - {r.status}", "",
                  "```bash", r.command, "```", "",
                  f"- exit code: `{r.exit_code}` / {r.seconds:.1f}s"]
        if r.category:
            lines.append(f"- category: **{r.category}** (judge: `{r.judge}`, "
                         f"confidence {r.confidence})")
        if r.explanation:
            lines.append(f"- diagnosis: {r.explanation}")
        if getattr(r, "after_fix", None):
            lines.append(f"- after the fix ran (still failing): **{r.after_fix['category']}** "
                         f"- {r.after_fix.get('explanation', '')}")
        if r.fix_command:
            lines.append(f"- proposed fix: `{r.fix_command}`")
        if r.exit_code != 0:
            lines += ["", "<details><summary>output tail</summary>", "",
                      "```", (r.output or "")[-2000:], "```", "", "</details>"]
    with open(base + ".md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    return {"md": base + ".md", "json": base + ".json"}
