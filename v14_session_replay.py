#!/usr/bin/env python3
"""
v14_session_replay.py

Purpose:
    CLEAN TEST:

    Using existing v14-style trade outputs, compare:

        A) Regular market hours only
        B) Regular + extended hours

This does NOT change strategy logic.
It assumes v14 trades already exist in the dataset.

We only evaluate whether session affects performance.

Usage:
    python3 v14_session_replay.py <trade_csv>
"""

import sys
import pandas as pd


REGULAR_START = "09:30"
REGULAR_END = "16:00"


def to_datetime(df):
    candidates = ["event_time", "matched_event_minute", "timestamp", "time"]

    col = None
    for c in candidates:
        if c in df.columns:
            col = c
            break

    if col is None:
        raise ValueError(f"No time column found. Tried {candidates}")

    df[col] = pd.to_datetime(df[col], errors="coerce")
    return df, col


def is_regular(ts):
    t = ts.time()
    start = pd.to_datetime(REGULAR_START).time()
    end = pd.to_datetime(REGULAR_END).time()
    return start <= t <= end


def summarize(df):
    if df.empty:
        return {
            "trades": 0,
            "total_pnl": 0.0,
            "avg_return_pct": 0.0,
            "win_rate": 0.0,
        }

    return {
        "trades": len(df),
        "total_pnl": float(df["paper_pnl_dollars"].sum()) if "paper_pnl_dollars" in df else 0.0,
        "avg_return_pct": float(df["trade_return_pct"].mean()) if "trade_return_pct" in df else 0.0,
        "win_rate": float((df["trade_return_pct"] > 0).mean()) if "trade_return_pct" in df else 0.0,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 v14_session_replay.py <csv>")
        sys.exit(1)

    path = sys.argv[1]
    df = pd.read_csv(path)

    df, tcol = to_datetime(df)
    df = df.dropna(subset=[tcol])

    # STRICT v14 assumption: only flash trades
    if "strategy" in df.columns:
        df = df[df["strategy"] == "flash_entry_after_dip"].copy()

    # classify sessions
    df["is_regular"] = df[tcol].apply(is_regular)

    regular_only = df[df["is_regular"]]
    all_sessions = df.copy()

    print("\n===== V14 SESSION TEST =====\n")

    r = summarize(regular_only)
    a = summarize(all_sessions)

    print("A) REGULAR HOURS ONLY")
    print(r)

    print("\nB) REGULAR + EXTENDED")
    print(a)

    print("\nDELTA (A - B)")
    diff = {k: r[k] - a[k] for k in r}
    print(diff)

    print("\nNOTE:")
    print("- This assumes dataset already represents v14 trades.")
    print("- We are only testing session dependency.")


if __name__ == "__main__":
    main()
