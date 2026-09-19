"""Skill Clinic CLI: run a skill's instructions for real, diagnose, re-verify."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

from rich.console import Console

from .extract import load_skill
from .html_report import write_html
from .judge import classify, classify_with_rules
from .report import INFRA_STATUS, count_infra_errors, decide_verdict, render_table, write_reports
from .security import analyse, headline, summarize
from .sandbox import ClinicConfigError, SandboxInfraError, run_steps, verify_fix

console = Console(width=max(shutil.get_terminal_size((120, 24)).columns, 118))


def _log(msg: str) -> None:
    console.print(msg, style="dim", highlight=False)


def _judge_summary(results) -> str:
    """Report the judge backend that was ACTUALLY used, counted from the rows."""
    used = Counter(r.judge for r in results if r.judge)
    if not used:
        return "none (no step needed diagnosing)"
    return ", ".join(f"{name} ×{n}" for name, n in used.most_common())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clinic",
        description="Run an agent skill's instructions in a fresh Daytona sandbox "
                    "and report what actually works.",
        epilog="exit codes: 0 = HEALTHY or FIXABLE, 1 = ENV_SPECIFIC or BROKEN "
               "(a real finding, not a crash), 2 = usage/configuration error.")
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

    try:
        skill = load_skill(args.skill, max_steps=args.max_steps)
    except FileNotFoundError as err:
        console.print(f"[red]cannot read that skill:[/] {err}")
        console.print("  Pass a directory containing SKILL.md/README.md, or the .md file itself, "
                      "e.g. [bold]fixtures/healthy-csv-summary[/]")
        return 2
    except OSError as err:
        console.print(f"[red]cannot read that skill:[/] {err}")
        return 2
    console.rule(f"[bold]Skill Clinic[/] - {skill['name']}")
    console.print(f"source     : {skill['file']}")
    console.print(f"steps found: {len(skill['steps'])}"
                  f"{'  (+ scripts/ dir)' if skill['has_scripts'] else ''}")
    console.print(f"judge      : {'nosana LLM (' + os.environ.get('LLM_MODEL', '?') + ')' if use_llm else 'rules (deterministic)'}")
    if not skill["steps"]:
        console.print("[red]No runnable shell steps found.[/]")
        return 2

    console.print("\n[bold]Phase 1[/] - running the skill in a fresh sandbox")
    try:
        results = run_steps(skill["dir"], skill["steps"], timeout=args.timeout,
                            log=_log, label="A")
    except ClinicConfigError as err:
        console.print(f"[red]configuration error:[/] {err}")
        return 2

    # Behaviour observation: what did each step actually TRY to do? The command text
    # gives the intent, the sandbox output gives the evidence (egress blocked, no
    # secrets present). This never touches the verdict - it is reported separately.
    for r in results:
        r.security = analyse(r.command, r.output)
    flagged = [r for r in results if r.security]
    if flagged:
        console.print("\n[bold]Security observations[/] - what the skill tried to do "
                      "(executed in a throwaway sandbox with egress blocked)")
        for r in flagged:
            blocked = any(f["rule"] == "egress_blocked" for f in r.security)
            missing = any(f["rule"] == "no_secret_present" for f in r.security)
            note = ("  (egress blocked by sandbox)" if blocked
                    else "  (no secret present in sandbox)" if missing else "")
            for f in r.security:
                if f["severity"] == "info":
                    continue
                colour = {"high": "red", "medium": "yellow"}.get(f["severity"], "dim")
                console.print(f"   [{colour}]SECURITY [{f['severity']}][/] "
                              f"{f['rule']}: {f['evidence']}{note}",
                              highlight=False)

    # INFRA_ERROR steps are our failure, not the skill's: never judged, never counted.
    failures = [r for r in results if not r.ok and r.status != INFRA_STATUS]
    if failures:
        console.print(f"\n[bold]Phase 2[/] - diagnosing {len(failures)} failure(s)")
    for r in failures:
        verdict = classify(r.command, r.output, r.exit_code, use_llm=use_llm,
                           on_fallback=lambda err: console.print(
                               f"   llm judge unavailable ({type(err).__name__}) -> rules",
                               style="yellow", highlight=False))
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
            try:
                code, out, secs = verify_fix(skill["dir"], prior, r.fix_command,
                                             timeout=args.timeout, log=_log)
            except ClinicConfigError as err:
                console.print(f"[red]configuration error:[/] {err}")
                return 2
            except SandboxInfraError as err:
                # Our sandbox broke, so the fix was never actually tested. Saying
                # "fix failed" here would blame the skill for our outage.
                r.seconds += err.seconds
                r.status = INFRA_STATUS
                r.output = (r.output + "\n\n[clinic] fix unverified (infrastructure):\n"
                            + str(err))[-4000:]
                console.print("      [magenta]INFRA_ERROR[/] fix unverified (infrastructure)")
                continue
            r.seconds += secs
            if code == 0:
                r.status = "FIXED"
                fixes_verified += 1
                console.print(f"      [green]FIXED[/] -> `{r.fix_command}` exit 0")
            else:
                r.output = (r.output + "\n\n[clinic] fix attempt output:\n" + out)[-4000:]
                # The fix ran and the step still fails - the NEW output may mean
                # something else entirely (e.g. the tool installed fine, but the
                # input file was never real). Re-read it with the deterministic
                # rules classifier; the row stays FAIL, the verdict is untouched.
                # Classified against the ORIGINAL step command: a fix like
                # `sudo apt-get install ...` would otherwise be read as env_specific
                # because of its own sudo, telling us nothing about the step.
                again = classify_with_rules(r.command, out, code)
                r.after_fix = {"category": again["category"],
                               "explanation": again["explanation"]}
                console.print(f"      [red]fix failed[/] (exit {code}) "
                              f"-> now: {again['category']}")

    verdict = decide_verdict(results)
    console.print()
    render_table(console, skill["name"], results)
    style = {"HEALTHY": "bold green", "FIXABLE": "bold cyan",
             "ENV_SPECIFIC": "bold yellow"}.get(verdict, "bold red")
    sec_line, sec_style = headline(results)
    console.print(f"VERDICT: [{style}]{verdict}[/]  "
                  f"({sum(1 for r in results if r.status == 'PASS')} pass / "
                  f"{fixes_verified} fixed / "
                  f"{sum(1 for r in results if r.status == 'FAIL')} fail)"
                  f"   [{sec_style}]{sec_line}[/]")
    sec = summarize(results)
    console.print(f"security: {sec['high']} high, {sec['medium']} medium"
                  f"{f", {sec['low']} low" if sec['low'] else ''}"
                  "  (observation only - the verdict is unchanged)",
                  style="dim")
    infra = count_infra_errors(results)
    if infra:
        console.print(f"infrastructure errors: {infra}  "
                      "(sandbox/SDK failures - excluded from the verdict, never judged)",
                      style="magenta")
    console.print(f"judge backends used: {_judge_summary(results)}")

    paths = write_reports(
        skill["name"], skill["file"], results, verdict, out_dir=args.out,
        meta={"fix_mode": args.fix, "llm_judge": use_llm, "security": sec,
              "llm_model": os.environ.get("LLM_MODEL") if use_llm else None})
    html_path = Path(paths["json"]).with_suffix(".html")
    write_html(json.loads(Path(paths["json"]).read_text(encoding="utf-8")), html_path)
    console.print(f"report: {paths['md']}")
    console.print(f"report: {paths['json']}")
    console.print(f"report: {html_path}")
    return 0 if verdict in ("HEALTHY", "FIXABLE") else 1


if __name__ == "__main__":
    sys.exit(main())
