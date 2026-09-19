# Skill Clinic report - `healthy-csv-summary`

- Source: `/home/pineapple/skill-clinic/fixtures/healthy-csv-summary/SKILL.md`
- Generated: 2026-09-19T14:33:21+0900
- **Verdict: HEALTHY**
- Steps: 4 (PASS 4, FIXED 0, FAIL 0, SKIP 0)

| # | Step | Command | Status | Category | Sec | Judge |
|---|------|---------|--------|----------|-----|-------|
| 1 | 1. Install pandas | `pip install pandas` | PASS | - | 1.0 | - |
| 2 | 2. Create a sample dataset | `printf 'name,team,score\nada,red,91\nlin,blue,78\nrio,red,6…` | PASS | - | 0.3 | - |
| 3 | 3. Run the summarizer | `python scripts/summarize.py data.csv` | PASS | - | 0.8 | - |
| 4 | 4. Check the output file | `test -f summary.txt && cat summary.txt` | PASS | - | 0.3 | - |

## Evidence

### 1. 1. Install pandas - PASS

```bash
pip install pandas
```

- exit code: `0` / 1.0s

### 2. 2. Create a sample dataset - PASS

```bash
printf 'name,team,score\nada,red,91\nlin,blue,78\nrio,red,64\nmax,blue,88\n' > data.csv
cat data.csv
```

- exit code: `0` / 0.3s

### 3. 3. Run the summarizer - PASS

```bash
python scripts/summarize.py data.csv
```

- exit code: `0` / 0.8s

### 4. 4. Check the output file - PASS

```bash
test -f summary.txt && cat summary.txt
```

- exit code: `0` / 0.3s
