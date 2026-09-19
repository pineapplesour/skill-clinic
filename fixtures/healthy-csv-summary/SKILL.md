---
name: csv-summary
description: Summarize a CSV file with pandas and print per-column statistics.
---

# CSV Summary

A tiny, boring, fully working skill. Use it as the control group.

## 1. Install pandas

```bash
pip install pandas
```

## 2. Create a sample dataset

```bash
printf 'name,team,score\nada,red,91\nlin,blue,78\nrio,red,64\nmax,blue,88\n' > data.csv
cat data.csv
```

## 3. Run the summarizer

```bash
python scripts/summarize.py data.csv
```

## 4. Check the output file

```bash
test -f summary.txt && cat summary.txt
```
