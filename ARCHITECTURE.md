# Architecture

1. `clinic/extract.py` — parses `SKILL.md`/`README.md`: walks fenced blocks, keeps shell-ish ones
   (`bash|sh|shell|console|zsh`, or untagged blocks whose lines look like commands), strips `$ `
   prompts and console output, drops pure comments, keeps a multi-line block as one step, and tags
   each step with the nearest preceding heading. Also flags a sibling `scripts/` dir.
2. `clinic/sandbox.py` — `SkillSandbox` is a context manager over one Daytona sandbox: `Daytona()` →
   `create()` → local `tarfile` gzip of the skill dir → `fs.upload_file` → `tar xzf` into
   `/home/daytona/skill`. Steps run via `process.exec("bash -lc '<cmd>'", cwd=WORKDIR, timeout=N)`,
   capturing exit code, the last 4000 chars of output and elapsed seconds. `delete()` always runs in
   `close()` / `__exit__`. `verify_fix()` opens a *separate* sandbox and replays the previously
   passing commands before the candidate fix.
3. `clinic/judge.py` — failure classification only. LLM path posts a strict-JSON prompt to the
   Nosana-hosted OpenAI-compatible endpoint and parses first `{` … last `}`; any error falls back to
   an ordered regex table. Returns `{category, explanation, fix_command|null, confidence, judge}`.
4. `clinic/report.py` — `decide_verdict()` (pure exit-code logic) plus a rich table and the
   `reports/<skill>-<timestamp>.{md,json}` evidence files with per-step output tails.
5. `clinic/cli.py` + `clinic.py` — three visible phases: run in sandbox A → diagnose failures →
   re-verify fixes in fresh sandbox B, printing sandbox ids and step numbers live for the stage demo.

Design rule threaded through all of it: **the model never decides pass/fail** — it only names a
category and proposes a command, and that command is believed only after it exits 0 for real.
