# Skill Clinic report - `stale-daytona-quickstart`

- Source: `/home/pineapple/skill-clinic/fixtures/stale-daytona-quickstart/SKILL.md`
- Generated: 2026-09-19T15:34:27+0900
- **Verdict: BROKEN**
- Steps: 6 (PASS 3, FIXED 1, FAIL 2, infrastructure errors 0)

| # | Step | Command | Status | Category | Time | Judge |
|---|------|---------|--------|----------|-----|-------|
| 1 | 1. Install the Python SDK | `pip install daytona` | PASS | - | 1.2 | - |
| 2 | 2. Install the Node SDK | `npm install @daytonaio/sdk` | PASS | - | 17.2 | - |
| 3 | 3. Pin the resolver | `pip install --use-feature=2020-resolver daytona` | FIXED | stale_command | -1.1 | nosana:qwen/qwen3.8-27b |
| 4 | 4. Add the legacy Node package | `npm install @daytonaio/daytona-sdk` | FAIL | stale_package | 1.1 | nosana:qwen/qwen3.8-27b |
| 5 | 5. Check your credentials | `python -c "import os; assert os.environ.get('DAYTONA_API_KE…` | FAIL | missing_secret | 0.4 | nosana:qwen/qwen3.8-27b |
| 6 | 6. Verify the SDK imports | `python -c "from daytona import Daytona; print('daytona sdk …` | PASS | - | 4.9 | - |

## Security observations

No injected or suspicious behaviour was observed in any step.

## Evidence

### 1. Install the Python SDK - PASS

```bash
pip install daytona
```

- exit code: `0` / 1.2s

### 2. Install the Node SDK - PASS

```bash
npm install @daytonaio/sdk
```

- exit code: `0` / 17.2s

### 3. Pin the resolver - FIXED

```bash
pip install --use-feature=2020-resolver daytona
```

- exit code: `2` / -1.1s
- category: **stale_command** (judge: `nosana:qwen/qwen3.8-27b`, confidence 0.97)
- diagnosis: The pip --use-feature=2020-resolver option is no longer valid in the current pip interface.
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

### 4. Add the legacy Node package - FAIL

```bash
npm install @daytonaio/daytona-sdk
```

- exit code: `1` / 1.1s
- category: **stale_package** (judge: `nosana:qwen/qwen3.8-27b`, confidence 0.95)
- diagnosis: The npm registry returned 404 for @daytonaio/daytona-sdk, indicating the package name/version is unavailable or was renamed/deprecated.

<details><summary>output tail</summary>

```
npm error code E404
npm error 404 Not Found - GET https://registry.npmjs.org/@daytonaio%2fdaytona-sdk - Not found
npm error 404
npm error 404  The requested resource '@daytonaio/daytona-sdk@*' could not be found or you do not have permission to access it.
npm error 404
npm error 404 Note that you can also install from a
npm error 404 tarball, folder, http url, or git url.
npm error A complete log of this run can be found in: /home/daytona/.npm/_logs/2026-09-19T06_33_39_309Z-debug-0.log

```

</details>

### 5. Check your credentials - FAIL

```bash
python -c "import os; assert os.environ.get('DAYTONA_API_KEY'), 'Set the DAYTONA_API_KEY environment variable'"
```

- exit code: `1` / 0.4s
- category: **missing_secret** (judge: `nosana:qwen/qwen3.8-27b`, confidence 0.98)
- diagnosis: The step requires the DAYTONA_API_KEY environment variable, which is a credential the skill does not provide or instruct the user to set.

<details><summary>output tail</summary>

```
Traceback (most recent call last):
  File "<string>", line 1, in <module>
    import os; assert os.environ.get('DAYTONA_API_KEY'), 'Set the DAYTONA_API_KEY environment variable'
                      ~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^
AssertionError: Set the DAYTONA_API_KEY environment variable

```

</details>

### 6. Verify the SDK imports - PASS

```bash
python -c "from daytona import Daytona; print('daytona sdk ready')"
```

- exit code: `0` / 4.9s
