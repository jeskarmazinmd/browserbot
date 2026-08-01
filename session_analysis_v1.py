#!/usr/bin/env python3
"""
session_analysis_v1.py

Purpose:
    Compare FLASH-DIP strategy performance in:

        1. Regular market hours (09:30–16:00 ET)
        2. Extended hours (16:00–09:30 ET)

Run:
    python3 session_analysis_v1.py /path/to/regime_test_trades.csv
"""

import sys
import pandas as pd
from datetime import datetime


def parse_time(df):
    candidates = ["event_time", "matched_event_minute", "timestamp", "time"]

    col = None
    for c in candidates:
        if c in df.columns:
            col = c
            break

    if col is None:
        raise ValueError(f"No time column found. Tried {candidates}. Columns: {list(df.columns)}")

    df[col] = pd.to_datetime(df[col], errors="coerce")
    return df, col


def classify_session(ts):
    t = ts.time()

    if (t >= datetime.strptime("09:30", "%H:%M").time()
        and t <= datetime.strptime("16:00", "%H:%M").time()):
        return "regular"
    return "extended"


def summarize(df):
    if df.empty:
        return {"trades": 0, "total_pnl": 0, "avg_return_pct": 0, "win_rate": 0}

    return {
        "trades": len(df),
        "total_pnl": float(df["paper_pnl_dollars"].sum()) if "paper_pnl_dollars" in df else 0,
        "avg_return_pct": float(df["trade_return_pct"].mean()) if "trade_return_pct" in df else 0,
        "win_rate": float((df["trade_return_pct"] > 0).mean()) if "trade_return_pct" in df else 0
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 session_analysis_v1.py <trade_csv>")
        sys.exit(1)

    file_path = sys.argv[1]
    df = pd.read_csv(file_path)

    df, tcol = parse_time(df)
    df = df.dropna(subset=[tcol])

    df["session"] = df[tcol].apply(classify_session)

    regular = df[df["session"] == "regular"]
    extended = df[df["session"] == "extended"]

    print("\n===== SESSION COMPARISON =====\n")

    r = summarize(regular)
    e = summarize(extended)

    print("REGULAR:")
    print(r)

    print("\nEXTENDED:")
    print(e)

    print("\nDELTA (REG - EXT):")
    print({k: r[k] - e[k] for k in r})


if __name__ == "__main__":
    main()
