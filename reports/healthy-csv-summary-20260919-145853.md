# Skill Clinic report - `healthy-csv-summary`

- Source: `/home/pineapple/skill-clinic/fixtures/healthy-csv-summary/SKILL.md`
- Generated: 2026-09-19T14:58:53+0900
- **Verdict: HEALTHY**
- Steps: 4 (PASS 4, FIXED 0, FAIL 0, infrastructure errors 0)

| # | Step | Command | Status | Category | Sec | Judge |
|---|------|---------|--------|----------|-----|-------|
| 1 | 1. Install pandas | `pip install pandas` | PASS | - | 0.9 | - |
| 2 | 2. Create a sample dataset | `printf 'name,team,score\nada,red,91\nlin,blue,78\nrio,red,6…` | PASS | - | 0.2 | - |
| 3 | 3. Run the summarizer | `python scripts/summarize.py data.csv` | PASS | - | 0.9 | - |
| 4 | 4. Check the output file | `test -f summary.txt && cat summary.txt` | PASS | - | 0.3 | - |

## Evidence

### 1. Install pandas - PASS

```bash
pip install pandas
```

- exit code: `0` / 0.9s

### 2. Create a sample dataset - PASS

```bash
printf 'name,team,score\nada,red,91\nlin,blue,78\nrio,red,64\nmax,blue,88\n' > data.csv
cat data.csv
```

- exit code: `0` / 0.2s

### 3. Run the summarizer - PASS

```bash
python scripts/summarize.py data.csv
```

- exit code: `0` / 0.9s

### 4. Check the output file - PASS

```bash
test -f summary.txt && cat summary.txt
```

- exit code: `0` / 0.3s
