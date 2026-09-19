"""Skill Clinic CLI: run a skill's instructions for real, diagnose, re-verify."""

from __future__ import annotations

import argparse
import os
import shutil
import sys

from rich.console import Console

from .extract import load_skill
from .judge import classify
from .report import decide_verdict, render_table, write_reports
from .sandbox import run_steps, verify_fix

console = Console(width=max(shutil.get_terminal_size((120, 24)).columns, 118))


def _log(msg: str) -> None:
    console.print(msg, style="dim", highlight=False)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clinic",
        description="Run an agent skill's instructions in a fresh Daytona sandbox "
                    "and report what actually works.")
    p.add_argument("skill", help="path to a skill directory or a SKILL.md/README.md")
    p.add_argument("--fix", action="store_true",
                   help="re-verify proposed fixes in a fresh sandbox")
    p.add_argument("--timeout", type=int, default=180, help="per-step timeout (s)")
    p.add_argument("--max-steps", type=int, default=12, help="max steps to run")
    p.add_argument("--no-llm", action="store_true",
                   help="skip the Nosana LLM judge, use deterministic rules only")
    p.add_argument("--out", default="reports", help="report output directory")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    use_llm = not args.no_llm and bool(os.environ.get("LLM_BASE_URL"))

    skill = load_skill(args.skill, max_steps=args.max_steps)
    console.rule(f"[bold]Skill Clinic[/] - {skill['name']}")
    console.print(f"source     : {skill['file']}")
    console.print(f"steps found: {len(skill['steps'])}"
                  f"{'  (+ scripts/ dir)' if skill['has_scripts'] else ''}")
    console.print(f"judge      : {'nosana LLM (' + os.environ.get('LLM_MODEL', '?') + ')' if use_llm else 'rules (deterministic)'}")
    if not skill["steps"]:
        console.print("[red]No runnable shell steps found.[/]")
        return 2

    console.print("\n[bold]Phase 1[/] - running the skill in a fresh sandbox")
    results = run_steps(skill["dir"], skill["steps"], timeout=args.timeout,
                        log=_log, label="A")

    failures = [r for r in results if not r.ok]
    if failures:
        console.print(f"\n[bold]Phase 2[/] - diagnosing {len(failures)} failure(s)")
    for r in failures:
        verdict = classify(r.command, r.output, r.exit_code, use_llm=use_llm)
        r.category = verdict["category"]
        r.explanation = verdict["explanation"]
        r.fix_command = verdict["fix_command"]
        r.confidence = verdict["confidence"]
        r.judge = verdict["judge"]
        console.print(f"  [step {r.index}] {r.category} "
                      f"(judge={r.judge}) fix={r.fix_command or '-'}", style="dim")

    fixes_verified = 0
    if args.fix and any(r.fix_command for r in failures):
        console.print("\n[bold]Phase 3[/] - re-verifying fixes in FRESH sandboxes")
        for r in failures:
            if not r.fix_command:
                continue
            prior = [x.command for x in results if x.index < r.index and x.ok]
            console.print(f"  [step {r.index}] replaying {len(prior)} passing step(s) + fix",
                          style="dim")
            code, out, secs = verify_fix(skill["dir"], prior, r.fix_command,
                                         timeout=args.timeout, log=_log)
            r.seconds += secs
            if code == 0:
                r.status = "FIXED"
                fixes_verified += 1
                console.print(f"      [green]FIXED[/] -> `{r.fix_command}` exit 0")
            else:
                r.output = (r.output + "\n\n[clinic] fix attempt output:\n" + out)[-4000:]
                console.print(f"      [red]fix failed[/] (exit {code})")

    verdict = decide_verdict(results)
    console.print()
    render_table(console, skill["name"], results)
    style = {"HEALTHY": "bold green", "FIXABLE": "bold cyan",
             "ENV_SPECIFIC": "bold yellow"}.get(verdict, "bold red")
    console.print(f"VERDICT: [{style}]{verdict}[/]  "
                  f"({sum(1 for r in results if r.status == 'PASS')} pass / "
                  f"{fixes_verified} fixed / "
                  f"{sum(1 for r in results if r.status == 'FAIL')} fail)")

    paths = write_reports(
        skill["name"], skill["file"], results, verdict, out_dir=args.out,
        meta={"fix_mode": args.fix, "llm_judge": use_llm,
              "llm_model": os.environ.get("LLM_MODEL") if use_llm else None})
    console.print(f"report: {paths['md']}")
    console.print(f"report: {paths['json']}")
    return 0 if verdict in ("HEALTHY", "FIXABLE") else 1


if __name__ == "__main__":
    sys.exit(main())
