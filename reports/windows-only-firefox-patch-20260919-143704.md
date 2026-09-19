# Skill Clinic report - `windows-only-firefox-patch`

- Source: `/home/pineapple/skill-clinic/fixtures/windows-only-firefox-patch/SKILL.md`
- Generated: 2026-09-19T14:37:04+0900
- **Verdict: BROKEN**
- Steps: 3 (PASS 0, FIXED 0, FAIL 3, SKIP 0)

| # | Step | Command | Status | Category | Sec | Judge |
|---|------|---------|--------|----------|-----|-------|
| 1 | 1. Locate the Firefox install | `powershell.exe -NoProfile -Command "Get-Item 'C:\Program Fi…` | FAIL | stale_command | 0.3 | rules |
| 2 | 2. Check the installed patch package | `ls -la /mnt/c/Users/$USER/AppData/Local/FirefoxShiftEnterPa…` | FAIL | env_specific | 0.3 | rules |
| 3 | 3. Verify the AutoConfig files are in place | `test -f "/mnt/c/Program Files/Mozilla Firefox/defaults/pref…` | FAIL | bug | 0.3 | rules |

## Evidence

### 1. 1. Locate the Firefox install - FAIL

```bash
powershell.exe -NoProfile -Command "Get-Item 'C:\Program Files\Mozilla Firefox\firefox.exe' | Select-Object -ExpandProperty VersionInfo | Select-Object ProductVersion"
```

- exit code: `127` / 0.3s
- category: **stale_command** (judge: `rules`, confidence 0.8)
- diagnosis: The CLI no longer accepts this subcommand/flag; the skill was written against an older version.

<details><summary>output tail</summary>

```
bash: line 1: powershell.exe: command not found

```

</details>

### 2. 2. Check the installed patch package - FAIL

```bash
ls -la /mnt/c/Users/$USER/AppData/Local/FirefoxShiftEnterPatch/
sha256sum /mnt/c/Users/$USER/AppData/Local/FirefoxShiftEnterPatch/autoconfig.js
```

- exit code: `1` / 0.3s
- category: **env_specific** (judge: `rules`, confidence 0.8)
- diagnosis: The step assumes a specific host OS, shell or privilege level.

<details><summary>output tail</summary>

```
ls: cannot access '/mnt/c/Users//AppData/Local/FirefoxShiftEnterPatch/': No such file or directory
sha256sum: /mnt/c/Users//AppData/Local/FirefoxShiftEnterPatch/autoconfig.js: No such file or directory

```

</details>

### 3. 3. Verify the AutoConfig files are in place - FAIL

```bash
test -f "/mnt/c/Program Files/Mozilla Firefox/defaults/pref/autoconfig.js" && echo "autoconfig loader present"
test -f "/mnt/c/Program Files/Mozilla Firefox/firefox.cfg" && echo "firefox.cfg present"
```

- exit code: `1` / 0.3s
- category: **bug** (judge: `rules`, confidence 0.4)
- diagnosis: The step failed for a reason specific to the skill's own logic or content.

<details><summary>output tail</summary>

```

```

</details>
