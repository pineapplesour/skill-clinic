"""Terminal table + markdown/json evidence report."""

from __future__ import annotations

import json
import os
import time

from rich.console import Console
from rich.table import Table

ENV_CATEGORIES = {"missing_secret", "env_specific", "network_blocked"}

_STATUS_STYLE = {
    "PASS": "bold green",
    "FIXED": "bold cyan",
    "FAIL": "bold red",
    "SKIP": "dim",
}


def decide_verdict(results) -> str:
    """Exit codes decide everything here - the model never votes."""
    failures = [r for r in results if r.status in ("FAIL", "FIXED")]
    if not failures:
        return "HEALTHY"
    unresolved = [r for r in failures if r.status != "FIXED"]
    if not unresolved:
        return "FIXABLE"
    if all((r.category in ENV_CATEGORIES) for r in unresolved):
        return "ENV_SPECIFIC"
    return "BROKEN"


def _truncate(text: str, width: int = 60) -> str:
    one_line = " ; ".join(text.splitlines())
    return one_line if len(one_line) <= width else one_line[: width - 1] + "…"


def render_table(console: Console, skill_name: str, results) -> None:
    table = Table(title=f"Skill Clinic - {skill_name}", header_style="bold magenta")
    table.add_column("#", justify="right", width=3)
    table.add_column("Step", max_width=26, overflow="ellipsis")
    table.add_column("Command", max_width=60, overflow="ellipsis")
    table.add_column("Status", width=6)
    table.add_column("Category", width=15)
    table.add_column("Sec", justify="right", width=5)
    table.add_column("Judge", width=12, overflow="ellipsis")
    for r in results:
        table.add_row(
            str(r.index), r.title, _truncate(r.command, 60),
            f"[{_STATUS_STYLE.get(r.status, '')}]{r.status}[/]",
            r.category or "-", f"{r.seconds:.1f}", r.judge or "-",
        )
    console.print(table)


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
                   for s in ("PASS", "FAIL", "FIXED", "SKIP")},
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
        f"FAIL {payload['counts']['FAIL']}, SKIP {payload['counts']['SKIP']})",
        "",
        "| # | Step | Command | Status | Category | Sec | Judge |",
        "|---|------|---------|--------|----------|-----|-------|",
    ]
    for r in results:
        cmd = _truncate(r.command, 60).replace("|", "\\|")
        lines.append(
            f"| {r.index} | {r.title} | `{cmd}` | {r.status} | "
            f"{r.category or '-'} | {r.seconds:.1f} | {r.judge or '-'} |"
        )
    lines.append("")
    lines.append("## Evidence")
    for r in results:
        lines += ["", f"### {r.index}. {r.title} - {r.status}", "",
                  "```bash", r.command, "```", "",
                  f"- exit code: `{r.exit_code}` / {r.seconds:.1f}s"]
        if r.category:
            lines.append(f"- category: **{r.category}** (judge: `{r.judge}`, "
                         f"confidence {r.confidence})")
        if r.explanation:
            lines.append(f"- diagnosis: {r.explanation}")
        if r.fix_command:
            lines.append(f"- proposed fix: `{r.fix_command}`")
        if r.exit_code != 0:
            lines += ["", "<details><summary>output tail</summary>", "",
                      "```", (r.output or "")[-2000:], "```", "", "</details>"]
    with open(base + ".md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    return {"md": base + ".md", "json": base + ".json"}
