#!/usr/bin/env python3
"""
trendline_scanner_v23.py
VERSION: 2026-05-10-regime-gate-comparison-v23

Purpose:
    Compare THREE gating styles:

    1. no_gate
    2. session_open_gate
    3. rolling_live_gate

Using cached intraday replay data.

Goal:
    Determine whether continuously rescanning the whole universe
    is actually worth the complexity versus a simpler session-level gate.

Outputs:
    ~/Desktop/regime_gate_comparison_YYYYMMDD_HHMMSS.csv

Run:
    cd ~/Desktop
    source scannerenv/bin/activate
    python3 trendline_scanner_v23.py
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


DESKTOP = Path.home() / "Desktop"
TRADES_GLOB = "regime_test_trades_*.csv"


# Session-open gate thresholds.
SESSION_MIN_MEDIAN_RETURN = -0.25
SESSION_MAX_DOWN_FRACTION = 0.60

# Rolling gate thresholds.
ROLLING_MIN_MEDIAN_RETURN = -0.50
ROLLING_MAX_DOWN_FRACTION = 0.65


def latest_trade_file():
    files = list(DESKTOP.glob(TRADES_GLOB))
    if not files:
        raise FileNotFoundError("Could not find regime_test_trades_*.csv")
    return max(files, key=lambda p: p.stat().st_mtime)


def summarize(df, label):
    if df.empty:
        return {
            "gate": label,
            "trade_count": 0,
            "total_pnl": 0.0,
            "avg_pnl": math.nan,
            "median_pnl": math.nan,
            "avg_return_pct": math.nan,
            "median_return_pct": math.nan,
            "win_rate_pct": math.nan,
            "hit_target_count": 0,
            "hit_stop_count": 0,
            "exit_eod_count": 0,
            "worst_trade": math.nan,
            "best_trade": math.nan,
            "worst_day": math.nan,
            "best_day": math.nan,
        }

    daily = df.groupby("trade_date")["paper_pnl_dollars"].sum()

    return {
        "gate": label,
        "trade_count": int(len(df)),
        "total_pnl": float(df["paper_pnl_dollars"].sum()),
        "avg_pnl": float(df["paper_pnl_dollars"].mean()),
        "median_pnl": float(df["paper_pnl_dollars"].median()),
        "avg_return_pct": float(df["trade_return_pct"].mean()),
        "median_return_pct": float(df["trade_return_pct"].median()),
        "win_rate_pct": float((df["trade_return_pct"] > 0).mean() * 100),
        "hit_target_count": int((df["outcome"] == "hit_target").sum()),
        "hit_stop_count": int((df["outcome"] == "hit_stop").sum()),
        "exit_eod_count": int((df["outcome"] == "exit_eod").sum()),
        "worst_trade": float(df["paper_pnl_dollars"].min()),
        "best_trade": float(df["paper_pnl_dollars"].max()),
        "worst_day": float(daily.min()) if len(daily) else math.nan,
        "best_day": float(daily.max()) if len(daily) else math.nan,
    }


def main():
    trade_file = latest_trade_file()

    print(f"Using: {trade_file}")

    df = pd.read_csv(trade_file)

    # Use flash entries only.
    if "strategy" in df.columns:
        df = df[df["strategy"] == "flash_entry_after_dip"].copy()

    # Use ideal fills only if available.
    if "execution_label" in df.columns:
        ideal = df[df["execution_label"] == "ideal_fills"]
        if not ideal.empty:
            df = ideal.copy()

    if df.empty:
        raise ValueError("No usable flash-entry rows found.")

    print(f"Rows loaded: {len(df)}")

    # Build regime stats by day from existing columns.
    regime = df.groupby("trade_date").agg(
        median_pre_crash_return_pct=("pre_crash_return_pct", "median"),
        down_fraction=("trade_return_pct", lambda x: float((x < 0).mean())),
        trade_count=("symbol", "count"),
    ).reset_index()

    print("\nDaily regime approximation:")
    print(regime.to_string(index=False))

    regime_by_day = {
        row["trade_date"]: row
        for _, row in regime.iterrows()
    }

    # ---------------------------------------------------------
    # 1. No gate
    # ---------------------------------------------------------
    no_gate = df.copy()

    # ---------------------------------------------------------
    # 2. Session-open gate
    #
    # Pretend we decide once near open whether tape is healthy.
    # ---------------------------------------------------------
    session_allowed_days = set()

    for _, row in regime.iterrows():
        good = (
            row["median_pre_crash_return_pct"] >= SESSION_MIN_MEDIAN_RETURN
            and row["down_fraction"] <= SESSION_MAX_DOWN_FRACTION
        )

        if good:
            session_allowed_days.add(row["trade_date"])

    session_gate = df[df["trade_date"].isin(session_allowed_days)].copy()

    # ---------------------------------------------------------
    # 3. Rolling gate
    #
    # Simulates continuous checking of universe conditions.
    # ---------------------------------------------------------
    rolling_rows = []

    for _, row in df.iterrows():
        r = regime_by_day[row["trade_date"]]

        good = (
            r["median_pre_crash_return_pct"] >= ROLLING_MIN_MEDIAN_RETURN
            and r["down_fraction"] <= ROLLING_MAX_DOWN_FRACTION
        )

        if good:
            rolling_rows.append(row)

    rolling_gate = pd.DataFrame(rolling_rows)

    # Summaries.
    results = [
        summarize(no_gate, "no_gate"),
        summarize(session_gate, "session_open_gate"),
        summarize(rolling_gate, "rolling_live_gate"),
    ]

    out = pd.DataFrame(results)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = DESKTOP / f"regime_gate_comparison_{timestamp}.csv"

    out.to_csv(outfile, index=False)

    print("\n===== REGIME GATE COMPARISON =====")
    print(out.to_string(index=False))

    print(f"\nSaved:\n{outfile}")

    print("\nInterpretation:")
    print("  session_open_gate = simpler architecture")
    print("  rolling_live_gate = safer but more complex")
    print("  Compare trade count vs quality improvement.")


if __name__ == "__main__":
    main()
