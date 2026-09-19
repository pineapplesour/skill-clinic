# Skill Clinic report - `stale-daytona-quickstart`

- Source: `/home/pineapple/skill-clinic/fixtures/stale-daytona-quickstart/SKILL.md`
- Generated: 2026-09-19T14:34:18+0900
- **Verdict: ENV_SPECIFIC**
- Steps: 6 (PASS 4, FIXED 1, FAIL 1, SKIP 0)

| # | Step | Command | Status | Category | Sec | Judge |
|---|------|---------|--------|----------|-----|-------|
| 1 | 1. Install the Python SDK | `pip install daytona` | PASS | - | 0.9 | - |
| 2 | 2. Install the Node SDK | `npm install @daytonaio/sdk` | PASS | - | 15.0 | - |
| 3 | 3. Pin the resolver | `pip install --use-feature=2020-resolver daytona` | FIXED | stale_command | 1.6 | rules |
| 4 | 4. Create your first sandbox from the CLI | `daytona sandbox create --name demo` | PASS | - | 0.6 | - |
| 5 | 5. Check your credentials | `python -c "import os; assert os.environ.get('DAYTONA_API_KE…` | FAIL | missing_secret | 0.5 | rules |
| 6 | 6. Verify the SDK imports | `python -c "from daytona import Daytona; print('daytona sdk …` | PASS | - | 1.9 | - |

## Evidence

### 1. 1. Install the Python SDK - PASS

```bash
pip install daytona
```

- exit code: `0` / 0.9s

### 2. 2. Install the Node SDK - PASS

```bash
npm install @daytonaio/sdk
```

- exit code: `0` / 15.0s

### 3. 3. Pin the resolver - FIXED

```bash
pip install --use-feature=2020-resolver daytona
```

- exit code: `2` / 1.6s
- category: **stale_command** (judge: `rules`, confidence 0.8)
- diagnosis: The CLI no longer accepts this subcommand/flag; the skill was written against an older version.
- proposed fix: `pip install daytona`

<details><summary>output tail</summary>

```

[optparse.groups]Usage:[/]   
  pip install \[options] <requirement specifier> \[package-index-options] ...
  pip install \[options] -r <requirements file> \[package-index-options] ...
  pip install \[options] [-e] <vcs project url> ...
  pip install \[options] [-e] <local project path> ...
  pip install \[options] <archive url/path> ...

option --use-feature: invalid choice: '2020-resolver' (choose from 'fast-deps', 'build-constraint', 'inprocess-build-deps', 'truststore', 'no-binary-enable-wheel-cache')

```

</details>

### 4. 4. Create your first sandbox from the CLI - PASS

```bash
daytona sandbox create --name demo
```

- exit code: `0` / 0.6s

### 5. 5. Check your credentials - FAIL

```bash
python -c "import os; assert os.environ.get('DAYTONA_API_KEY'), 'Set the DAYTONA_API_KEY environment variable'"
```

- exit code: `1` / 0.5s
- category: **missing_secret** (judge: `rules`, confidence 0.8)
- diagnosis: The step needs a credential or environment variable that the skill never tells you to set.

<details><summary>output tail</summary>

```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
    import os; assert os.environ.get('DAYTONA_API_KEY'), 'Set the DAYTONA_API_KEY environment variable'
                      ~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^
AssertionError: Set the DAYTONA_API_KEY environment variable

```

</details>

### 6. 6. Verify the SDK imports - PASS

```bash
python -c "from daytona import Daytona; print('daytona sdk ready')"
```

- exit code: `0` / 1.9s
