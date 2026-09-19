# Skill Clinic

Run an agent skill's instructions for real, in a fresh sandbox, and find out what still works.

## Problem

Agent skills (`SKILL.md` / `README.md` instruction files) are increasingly AI-written, and they rot
silently: a package gets renamed, a CLI drops a subcommand, a step quietly needs a secret nobody
mentioned. Nothing fails loudly — the skill just makes your agent fail later, in production.

## What it does

Skill Clinic parses the runnable steps out of a skill file, **executes them for real** inside a
fresh Daytona sandbox, records per-step exit code / output / duration, classifies every failure with
a cheap LLM judge (or deterministic rules), proposes a fix, and **re-verifies that fix in another
fresh sandbox** before claiming anything. Output is a terminal table plus a per-step evidence report
in Markdown and JSON.

## Pipeline

```
SKILL.md ──▶ extract ──▶ Daytona sandbox A ──▶ per-step exit codes
             (steps)     (state persists)       │
                                                ├─ exit 0 ──────────────▶ PASS
                                                └─ exit != 0 ──▶ judge ──▶ category + fix_command
                                                                            │
                                            Daytona sandbox B (FRESH) ◀─────┘  --fix
                                            replay passing steps + fix
                                                     │
                                            exit 0 ──▶ FIXED   exit != 0 ──▶ FAIL
                                                     │
                                            report ──▶ table + reports/<skill>-<ts>.{md,json}
```

## Daytona usage

Every step in a report was produced by these SDK calls — nothing is simulated:

| Call | Where | Why |
|------|-------|-----|
| `Daytona()` | `clinic/sandbox.py:72` | client from `DAYTONA_API_KEY` / `DAYTONA_TARGET` |
| `client.create()` | `clinic/sandbox.py:78` | fresh disposable sandbox per run (~1.5-3s warm) |
| `sandbox.fs.upload_file(archive, "skill.tar.gz")` | `clinic/sandbox.py:101` | ship the whole skill dir (`tarfile` gzip, `clinic/sandbox.py:59`) |
| `sandbox.process.exec("bash -lc 'tar xzf ...'", timeout=120)` | `clinic/sandbox.py:102` | unpack into `/home/daytona/skill` |
| `sandbox.process.exec(cmd, cwd=WORKDIR, timeout=...)` | `clinic/sandbox.py:121` | run one skill step; `exit_code` is the only source of truth |
| `sandbox.delete()` | `clinic/sandbox.py:91` | in `close()`, always reached via `__exit__` / `finally` |

Sandbox A runs all steps sequentially so state persists (installs from step 1 are visible in step 4).
Fix re-verification always uses a **new** sandbox (`verify_fix`, `clinic/sandbox.py:132`) so a fix can
never be credited to leftover state.

Field note: the default Daytona image already ships a `daytona` binary — it is the **toolbox daemon**,
not the CLI, and invoking it exits 0. That is exactly the kind of false PASS this tool exists to expose,
so our fixture avoids it (see Limitations).

## Nosana usage

The failure judge is an OpenAI-compatible chat completion against a **Nosana-hosted Ollama/vLLM
endpoint**, configured purely by environment:

- `LLM_BASE_URL` — the Nosana job's inference endpoint (`clinic/judge.py:classify_with_llm`)
- `LLM_MODEL` — e.g. `qwen2.5-coder:7b`
- `LLM_API_KEY` — defaults to `"x"` for open endpoints

The endpoint is provisioned by `nosana_deploy.py` (the `nosana/` module lands separately). Each report
row records which backend judged it: `judge: "nosana:<model>"` or `judge: "rules"`. If `LLM_BASE_URL`
is unset, the call errors, or the JSON is unparseable, Skill Clinic silently falls back to the
deterministic regex classifier — the pipeline never hard-depends on the GPU being up.

## Quickstart

```bash
python -m venv .venv && .venv/bin/pip install daytona openai requests rich pytest
set -a; source .env; set +a        # DAYTONA_API_KEY, DAYTONA_TARGET, (optional) LLM_BASE_URL
python clinic.py fixtures/healthy-csv-summary --no-llm
python clinic.py fixtures/stale-daytona-quickstart --fix
```

```
python clinic.py <skill-dir-or-SKILL.md> [--fix] [--timeout 180] [--max-steps 12] [--no-llm]
```

## Fixtures & expected results

| Fixture | Expected |
|---------|----------|
| `fixtures/healthy-csv-summary` | 4/4 PASS, verdict **HEALTHY** (the control group) |
| `fixtures/stale-daytona-quickstart` | step 3 `pip --use-feature=2020-resolver` → `stale_command` → **FIXED**; step 4 `npm install @daytonaio/daytona-sdk` → `stale_package` (scope renamed to `@daytona`) → **FIXED**; step 5 `DAYTONA_API_KEY` assert → `missing_secret`, no fix invented → **FAIL**; verdict **ENV_SPECIFIC** |

Step 2 (`npm install @daytonaio/sdk`) prints npm's deprecation notice but exits 0, so it is reported
as PASS. We do not downgrade a step the tool itself considered successful.

## Judging rules

- **The exit code decides pass/fail. Always. In code.** (`clinic/report.py:decide_verdict`,
  `clinic/sandbox.py:StepResult.ok`)
- The model only *labels* an already-failed step with one of:
  `stale_package`, `stale_command`, `missing_secret`, `env_specific`, `network_blocked`, `bug`, `unknown`.
- A proposed fix is only ever reported as `FIXED` after it exits 0 in a fresh sandbox.
- `missing_secret` never gets a `fix_command` — we do not invent credentials.
- Verdicts: `HEALTHY` (all pass) / `FIXABLE` (every failure fixed on re-verify) /
  `ENV_SPECIFIC` (remaining failures are only secret/env/network) / `BROKEN`.

## Limitations

- Arbitrary outbound internet is blocked in the sandbox; PyPI, npm and GitHub work. Anything else is
  correctly but bluntly labelled `network_blocked`.
- Only fenced shell blocks are executed; prose instructions ("open the dashboard and click…") are invisible.
- A step that exits 0 while doing nothing useful (deprecation warnings, the toolbox-daemon case above)
  still counts as PASS — exit codes are honest, not smart.
- Fix suggestions are deliberately conservative: single-command, no credential invention, no file edits.
- Secrets are never uploaded to the sandbox; that is *why* `missing_secret` shows up.

## Team

Built at the hackathon by **pineapplesour** — Daytona for execution, Nosana for the judge.
