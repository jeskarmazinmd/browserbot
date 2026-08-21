#!/usr/bin/env python3
"""Build today's broad research-universe cache, then exit.

This script deliberately does not poll live quotes and places no orders.
Long-term and liquidity measurements are retained as descriptive columns;
they no longer decide whether a symbol is admitted.
"""

from datetime import datetime, timezone
from pathlib import Path
import os
import re
import time
import json

from universe_tags import build_tags

import pandas as pd

from trendline_scanner_v25_live_schwab import (
    BATCH_SIZE,
    DAILY_CACHE_DIR,
    compute_longterm_features,
    load_daily_close,
    load_symbols,
    now_label,
    refresh_daily_cache_batch,
)

try:
    from trendline_scanner_v25_live_schwab import (
        compute_liquidity_features,
        load_daily_volume,
    )
except ImportError:
    compute_liquidity_features = None
    load_daily_volume = None

try:
    from trendline_scanner_v25_live_schwab import load_bad_symbols
except ImportError:
    def load_bad_symbols():
        return set()

BAD_TICKERS = {"SEMR", "FOLD", "DAWN", "CTRA", "CUK"}
DATA_DIR = Path("/data")

# Infrastructure guardrail only. Zero means no cap.
RESEARCH_UNIVERSE_MAX_SYMBOLS = int(os.environ.get("RESEARCH_UNIVERSE_MAX_SYMBOLS", "0") or 0)

# Conservative syntax accepted by Schwab's quote endpoint.
VALID_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,11}$")


def _clean_symbols(raw_symbols):
    bad_symbols = {str(x).upper().strip() for x in load_bad_symbols()}
    seen = set()
    cleaned = []
    rejected = {"blank": 0, "bad_ticker": 0, "bad_symbol_file": 0, "invalid_format": 0, "duplicate": 0}

    for raw in raw_symbols:
        symbol = str(raw or "").upper().strip()
        if not symbol:
            rejected["blank"] += 1
            continue
        if symbol in BAD_TICKERS:
            rejected["bad_ticker"] += 1
            continue
        if symbol in bad_symbols:
            rejected["bad_symbol_file"] += 1
            continue
        if not VALID_SYMBOL.fullmatch(symbol):
            rejected["invalid_format"] += 1
            continue
        if symbol in seen:
            rejected["duplicate"] += 1
            continue
        seen.add(symbol)
        cleaned.append(symbol)

    if RESEARCH_UNIVERSE_MAX_SYMBOLS > 0:
        cleaned = cleaned[:RESEARCH_UNIVERSE_MAX_SYMBOLS]

    return cleaned, rejected


def _safe_features(symbol):
    row = {
        "symbol": symbol,
        "feature_status": "NO_HISTORY",
        "pass_longterm": None,
        "pass_liquidity": None,
    }

    try:
        close = load_daily_close(symbol)
        features = compute_longterm_features(close)
        if features:
            row.update(features)
            row["feature_status"] = "OK"
    except Exception as exc:
        row["feature_status"] = f"LONGTERM_ERROR:{type(exc).__name__}"

    if compute_liquidity_features is not None and load_daily_volume is not None:
        try:
            liquidity = compute_liquidity_features(load_daily_volume(symbol))
            if liquidity:
                row.update(liquidity)
        except Exception as exc:
            row["liquidity_status"] = f"ERROR:{type(exc).__name__}"

    row["legacy_eligible"] = bool(
        row.get("pass_longterm") is True
        and row.get("pass_liquidity", True) is not False
    )
    return row


def main():
    started = time.perf_counter()
    DAILY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    output = DATA_DIR / f"research_universe_{today}.csv"
    compatibility_output = DATA_DIR / f"eligible_symbols_{today}.csv"
    manifest_output = DATA_DIR / f"universe_manifest_{today}.json"

    raw_symbols = load_symbols()
    symbols, rejected = _clean_symbols(raw_symbols)

    if not symbols:
        raise RuntimeError("Research-universe builder produced zero clean symbols")

    print(
        f"[{now_label()}] Building broad research universe "
        f"raw={len(raw_symbols)} clean={len(symbols)} rejected={rejected}",
        flush=True,
    )

    today_ts = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    refreshed, missing_bad = refresh_daily_cache_batch(
        symbols, today=today_ts, batch_size=BATCH_SIZE
    )

    rows = []
    for index, symbol in enumerate(symbols, start=1):
        rows.append(_safe_features(symbol))
        if index % 500 == 0:
            print(
                f"[{now_label()}] Research-universe feature progress: "
                f"{index}/{len(symbols)}",
                flush=True,
            )

    frame = pd.DataFrame(rows)
    if "last_price" not in frame.columns:
        frame["last_price"] = None
    frame["universe_memberships"] = frame.apply(lambda r: build_tags(r), axis=1)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbols": {
            str(r["symbol"]).upper(): {
                "primary_universe": "RESEARCH",
                "universe_memberships": r["universe_memberships"],
                "sampling_tier": "BROAD",
                "dynamic_promoted": False,
                "legacy_eligible": bool(r.get("legacy_eligible", False)),
            }
            for _, r in frame.iterrows()
        }
    }
    manifest_tmp = manifest_output.with_suffix(".json.tmp")
    manifest_tmp.write_text(json.dumps(manifest, indent=2))
    manifest_tmp.replace(manifest_output)

    # The new canonical cache contains every clean symbol and descriptive tags.
    tmp = output.with_suffix(".csv.tmp")
    frame.to_csv(tmp, index=False)
    tmp.replace(output)

    # Compatibility cache keeps existing supervisor/runner code working.
    compatibility_tmp = compatibility_output.with_suffix(".csv.tmp")
    frame.to_csv(compatibility_tmp, index=False)
    compatibility_tmp.replace(compatibility_output)

    legacy_count = int(frame["legacy_eligible"].fillna(False).sum())
    print(
        f"[{now_label()}] Saved broad research universe | "
        f"symbols={len(frame)} legacy_eligible={legacy_count} "
        f"daily_refreshed={refreshed} daily_missing_bad={missing_bad} "
        f"cap={RESEARCH_UNIVERSE_MAX_SYMBOLS or 'none'} "
        f"elapsed={time.perf_counter() - started:.1f}s | "
        f"output={output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
