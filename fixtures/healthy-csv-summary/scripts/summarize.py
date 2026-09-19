#!/usr/bin/env python3
"""Summarize a CSV: row count, columns, numeric stats, per-team means."""

import sys

import pandas as pd


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "data.csv"
    df = pd.read_csv(path)
    lines = [
        f"rows: {len(df)}",
        f"columns: {', '.join(df.columns)}",
        f"mean score: {df['score'].mean():.2f}",
        f"max score: {df['score'].max()} ({df.loc[df['score'].idxmax(), 'name']})",
    ]
    for team, mean in df.groupby("team")["score"].mean().items():
        lines.append(f"team {team}: {mean:.2f}")
    text = "\n".join(lines)
    print(text)
    with open("summary.txt", "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
