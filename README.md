# Skill Clinic

Run an agent skill's instructions for real, in a fresh sandbox, and find out what still works.

## Problem

Picture the team that maintains **40 `SKILL.md` files for their Claude Code / Codex users** — install
guides, deploy runbooks, SDK quickstarts. Those files are increasingly AI-written, and they rot
silently: a package gets renamed, a CLI drops a subcommand, a step quietly needs a secret nobody
mentioned. Nothing fails loudly. CI does not cover them, because they are prose, not code. The team
finds out when a user's agent confidently follows step 4 and breaks something in production.

They cannot hand-run 40 instruction files every week, and reading them proves nothing — the only
honest test is to *execute* them somewhere clean and look at the exit codes.

## Why this is not AgentEval / Airlock / ChaosAgent / Code Quintet

- **AgentEval** scores how well an *agent* performed a task; Skill Clinic scores the *instruction file* the agent was given.
- **Airlock** sandboxes an agent so its actions cannot hurt you; Skill Clinic uses the sandbox as a test rig, not a containment wall.
- **ChaosAgent** injects faults to see whether a *system* survives; Skill Clinic injects nothing — it runs the documented steps exactly as written and reports what reality returns.
- **Code Quintet** reviews *code* with models; Skill Clinic never asks a model whether something works — the exit code decides, and a fix is only believed after it exits 0 in a **second fresh sandbox**.

## What it does

Skill Clinic parses the runnable steps out of a skill file, **executes them for real** inside a
fresh Daytona sandbox, records per-step exit code / output / duration, classifies every failure with
a cheap LLM judge (or deterministic rules), proposes a fix, and **re-verifies that fix in another
fresh sandbox** before claiming anything. Output is a terminal table plus a per-step evidence report
in Markdown, JSON and a self-contained HTML page you can open or attach straight from `reports/`.

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
                                            report ──▶ table + reports/<skill>-<ts>.{md,json,html}
```

## Daytona usage

Every step in a report was produced by these SDK calls — nothing is simulated:

| Call | Where | Why |
|------|-------|-----|
| `Daytona()` | `clinic/sandbox.py:90` | client from `DAYTONA_API_KEY` / `DAYTONA_TARGET` |
| `client.create()` | `clinic/sandbox.py:110` | fresh disposable sandbox per run (~1.5-3s warm) |
| `sandbox.fs.upload_file(archive, "skill.tar.gz")` | `clinic/sandbox.py:138` | ship the whole skill dir (`tarfile` gzip, `clinic/sandbox.py:75`) |
| `sandbox.process.exec("bash -lc 'tar xzf ...'", timeout=120)` | `clinic/sandbox.py:139` | unpack into `/home/daytona/skill` |
| `sandbox.process.exec(cmd, cwd=WORKDIR, timeout=...)` | `clinic/sandbox.py:158` | run one skill step; `exit_code` is the only source of truth |
| `sandbox.delete()` | `clinic/sandbox.py:128` | in `close()`, always reached via `__exit__` / `finally` |

Sandbox A runs all steps sequentially so state persists (installs from step 1 are visible in step 4).
Fix re-verification always uses a **new** sandbox (`verify_fix`, `clinic/sandbox.py:199`) so a fix can
never be credited to leftover state.

A sandbox is never leaked: if the upload into a freshly created sandbox fails, `__enter__` calls
`close()` before re-raising (`clinic/sandbox.py:__enter__`). And when the Daytona SDK or the network
itself fails on a step, that step is recorded as **`INFRA_ERROR`**, not as a skill failure — it is
excluded from the verdict, never shown to the judge, and reported separately as
`infrastructure errors: N`.

Field note: the default Daytona image already ships a `daytona` binary — it is the **toolbox daemon**,
not the CLI, and invoking it exits 0. That is exactly the kind of false PASS this tool exists to expose,
so our fixture avoids it (see Limitations).

## Nosana usage

The failure judge runs on a **credit-paid Nosana GPU job** that `nosana_deploy.py` provisions end to
end — no wallet, no manual dashboard step:

```bash
.venv/bin/python nosana_deploy.py --template qwen3-5-9b --market nvidia-3090 --wait
```

1. fetch the official Nosana template job definition (Ollama server + model) — `GET /api/templates/<id>`
2. pin that job definition to **IPFS** (the public Pinata key shipped as nosana-kit's default)
3. `POST /api/jobs/list` with the IPFS hash + market → job address + run account, **paid with account credits**
4. poll `https://<job>.node.k8s.prd.nos.ci/api/tags` until the model server answers 200
5. print the three variables to export:

```
export LLM_BASE_URL=https://<job>.node.k8s.prd.nos.ci/v1
export LLM_MODEL=qwen3.5:9b
export LLM_API_KEY=x
```

`clinic/judge.py` consumes exactly those three variables through an **OpenAI-compatible client**
(`classify_with_llm`), so the GPU job is a drop-in judge backend. Lifecycle is managed from the same
script: `.venv/bin/python nosana_deploy.py --status <job>` and `.venv/bin/python nosana_deploy.py --stop <job>`.

Every report row records which backend actually judged it — `judge: "nosana:<model>"` or
`judge: "rules"` — and the CLI prints the tally at the end (`judge backends used: nosana:qwen3.5:9b ×2,
rules ×1`). If the LLM call fails, the CLI says so out loud (`llm judge unavailable (APIConnectionError)
-> rules`) and falls back to the deterministic classifier; the pipeline never hard-depends on the GPU
being up, and it never pretends the GPU judged something it did not.

## Quickstart

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env                # then fill in DAYTONA_API_KEY (and NOSANA_API_KEY)
set -a; source .env; set +a         # DAYTONA_API_KEY, DAYTONA_TARGET, (optional) LLM_BASE_URL
.venv/bin/python clinic.py fixtures/healthy-csv-summary --no-llm
.venv/bin/python clinic.py fixtures/stale-daytona-quickstart --fix
.venv/bin/python -m pytest -q       # offline tests, no sandbox needed
```

```
clinic.py <skill-dir-or-SKILL.md> [--fix] [--timeout 180] [--max-steps 12] [--no-llm] [--out DIR]
```

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | verdict **HEALTHY** or **FIXABLE** |
| `1` | verdict **ENV_SPECIFIC** or **BROKEN** — *a finding, not a crash*: the tool worked, the skill did not |
| `2` | usage or configuration error (no runnable steps, unreadable skill path, missing/invalid `DAYTONA_API_KEY`) |

A demo that ends with exit `1` is the tool succeeding at its job.

## Fixtures & expected results

| Fixture | Expected |
|---------|----------|
| `fixtures/healthy-csv-summary` | 4/4 PASS, verdict **HEALTHY** (the control group) |
| `fixtures/stale-daytona-quickstart` | step 3 `pip --use-feature=2020-resolver` → `stale_command` → **FIXED**; step 4 `npm install @daytonaio/daytona-sdk` → `stale_package` (scope renamed to `@daytona`) → **FIXED**; step 5 `DAYTONA_API_KEY` assert → `missing_secret`, no fix invented → **FAIL**; verdict **ENV_SPECIFIC** |
| `fixtures/injected-notes-skill` | a plausible markdown-notes skill with **prompt-injected** steps: `curl … | sh`, `cat ~/.ssh/id_rsa | curl -X POST …`, `env | base64 | curl …`, `>> ~/.bashrc`. Executed for real in the sandbox: `SECURITY: SUSPICIOUS (4 high)`, every egress attempt recorded as blocked. The verdict is untouched — security findings are observations. |
| `fixtures/windows-only-firefox-patch` | 3/3 FAIL, all `env_specific` (powershell.exe, `/mnt/c/...`), no fix invented → verdict **ENV_SPECIFIC** |

Step 2 (`npm install @daytonaio/sdk`) prints npm's deprecation notice but exits 0, so it is reported
as PASS. We do not downgrade a step the tool itself considered successful.

The table above is the `--no-llm` (deterministic rules) result, so it is reproducible without a GPU.
With `LLM_BASE_URL` set, the pass/fail column is unchanged — exit codes still decide it — but the
**Category** column comes from the Nosana-hosted model instead of the rules, and each row records
which one judged it (`judge: nosana:<model>` vs `judge: rules`).

## Judging rules

- **The exit code decides pass/fail. Always. In code.** (`clinic/report.py:decide_verdict`,
  `clinic/sandbox.py:StepResult.ok`)
- The model only *labels* an already-failed step with one of:
  `stale_package`, `stale_command`, `missing_tool`, `example_snippet`, `missing_secret`, `env_specific`,
  `network_blocked`, `bug`, `unknown`.
- A proposed fix is only ever reported as `FIXED` after it exits 0 in a fresh sandbox.
- `missing_secret` never gets a `fix_command` — we do not invent credentials.
- Before any error-message heuristic, the **command text itself** is prechecked for host-specific
  commands (`powershell`, `*.exe`, `/mnt/c/...`, `C:\...`, `wsl`, `brew`, `sudo`, `systemctl`,
  `osascript`) and classified `env_specific` (`clinic/judge.py:_ENV_CMD`).
- The sudo asymmetry is deliberate: a skill that *requires* `sudo` is flagged `env_specific` because it
  assumes privileges on the reader's machine, while the clinic's own `missing_tool` fix uses `sudo` only
  inside the throwaway sandbox where it is harmless — and that fix is reported as a proposal, never
  applied to your machine.

### Known rot rules

Fix proposals come from a small **published** table of documented interface changes
(`clinic/judge.py:_suggest_fix`) — not from anything tailored to our fixtures:

| # | Rot pattern | Rewrite |
|---|-------------|---------|
| 1 | `daytona sandbox <verb>` | `daytona <verb>` — the noun layer was dropped from the CLI |
| 2 | Removed pip flags | strip `--use-feature=…`, `--egg`, `--process-dependency-links` |
| 3 | `@daytonaio/*` npm package answering 404/deprecated | `@daytona/sdk` (scope rename) |
| 4 | An option the tool itself reports as unknown (`no such option: --x`, `unrecognized arguments: --x`) | strip that exact flag |

Anything outside this table gets **no** fix — we do not guess. Every proposal still has to exit 0 in a
fresh sandbox before it is reported as `FIXED`.
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

## Security: what a skill *tries* to do when actually run

Prompt injection is now arriving through skills: a helpful-looking SKILL.md with one extra step such as
`curl … | sh`, `cat ~/.ssh/id_rsa | curl -X POST …`, `env | base64 | curl …` or `echo '…' >> ~/.bashrc`.
Reading the file misses it; a static linter sees "a shell command". Skill Clinic runs every step inside a
throwaway Daytona sandbox whose egress is restricted, so the injected step is executed *for real* and the
report shows what it attempted and what stopped it:

- `clinic/security.py` flags commands by rule (`remote_code_exec`, `credential_exfil`, `credential_access`,
  `obfuscation`, `persistence`, `destructive`, `suspicious_egress`) and turns sandbox evidence into observations
  (`egress_blocked`, `no_secret_present`).
- The CLI prints `SECURITY: SUSPICIOUS (n high)` next to the verdict; the md/html reports get a
  "Security observations" section. The pass/fail verdict is **not** changed by security findings — they are
  observations with evidence, and a human decides.
- Fixture: `fixtures/injected-notes-skill` (a plausible notes indexer with four injected steps). Real run today:
  `reports/injected-notes-skill-*.md` → `SECURITY: SUSPICIOUS (4 high)`, `security: 4 high, 1 medium, 4 low`,
  with the exfil attempts recorded as blocked by the sandbox network policy and no secret present to leak.

Why this needs Daytona rather than a local VM: every skill gets its own fresh machine, nothing of yours is on it,
and it is deleted afterwards. The skill can try; it cannot reach anything.

## Evidence: third-party skills we did not write

Run unmodified from their public repos (see `fixtures/third-party/*/SOURCE.txt`), each in a fresh Daytona sandbox:

| Skill | Steps | Result | What the clinic found |
|---|---|---|---|
| `daytona/skills` — `daytona` (Daytona's own skill) | 1 bash step | HEALTHY | `pip install daytona` still resolves. Its Python blocks are not executed (they need `DAYTONA_API_KEY`, which the skill correctly tells you to set first). |
| `anthropics/skills` — `pdf` | 4 | BROKEN, 4× `missing_tool` | `pdftotext`, `qpdf`, `pdftk`, `pdfimages` do not exist on a fresh machine; the clinic proposed `sudo apt-get install poppler-utils / qpdf / pdftk-java` and re-ran in fresh sandboxes — the tools install, but the snippets then fail because they reference example files (`input.pdf`) that the skill never creates. |
| `anthropics/skills` — `docx` | 3 | BROKEN | Same pattern: illustrative snippets (`unzip doc.docx`, `python scripts/comment.py`) that assume files the reader has, so they cannot be executed as written. |

Reports: `reports/daytona-official-*.md`, `reports/anthropic-pdf-*.md`, `reports/anthropic-docx-*.md`.
The honest lesson these three runs teach: a lot of SKILL.md content is *illustration*, not *instruction*. A skill that
wants to be executable should mark which blocks are runnable and ship its own fixtures — exactly what the clinic's own
fixtures do.

## Evidence: Nosana-judged run

GPU jobs provisioned today with `nosana_deploy.py` (credit-paid, via `POST /jobs/list`; all four left in the
account's job history so a judge can verify them):

| Job address | Market | Template | Credits reserved | Posted (KST) |
|---|---|---|---|---|
| `61ZrXT3m5zhaHxtBFef6pwrvYEJqcH9KVgXJUQ9eiLfG` | nvidia-3090 | qwen3-5-9b (Ollama `qwen3.5:9b`) | $0.175 | 14:29 |
| `CEfGCgWN5ncbCfrLCUBqQNMPnVBPoEN5tH6wwMDXdDrS` | nvidia-4090 | gemma3-4b (Ollama `gemma3:4b-it-qat`) | $0.364 | 14:29 |
| `FEeohir6hBTYqtM6LT5d7JLEQiVrhHofGKPxmFRDZfXW` | nvidia-4090 | gemma3-4b on the market's pre-cached `ollama:0.15.4` image | $0.364 | 14:48 |
| `2VDxfcfyncNFLfmg4JEPBq574jWuV9VMBiAr1iiPaq1M` | nvidia-4090 | vLLM `Qwen/Qwen2.5-3B-Instruct` on the market's pre-cached `vllm-openai:v0.10.2` image (OpenAI-compatible `/v1`) | $0.364 | 15:00 |

Endpoints: `https://<job>.node.k8s.prd.nos.ci` (Ollama; OpenAI-compatible under `/v1`). Explorer: `https://explore.nosana.com/jobs/<job>`.

Honest status at the time of writing: the nodes accepted all four jobs within seconds (state RUNNING, node assigned) but
were still pulling the model image ("Service Initializing", HTTP 503) for 20+ minutes. The recorded run below is appended
the moment an endpoint answers; if this section still ends here, the LLM judge was never reached and every report in
`reports/` says so explicitly (`judge: rules`). We do not fake it.

