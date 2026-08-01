#!/usr/bin/env python3
"""Build today's long-term eligibility cache, then exit.

This deliberately performs no live quote polling and places no orders.
"""

from datetime import datetime, timezone
from pathlib import Path
import time

import pandas as pd

from trendline_scanner_v25_live_schwab import (
    BATCH_SIZE,
    DAILY_CACHE_DIR,
    compute_liquidity_features,
    compute_longterm_features,
    load_daily_close,
    load_daily_volume,
    load_symbols,
    now_label,
    refresh_daily_cache_batch,
)

BAD_TICKERS = {"SEMR", "FOLD", "DAWN", "CTRA", "CUK"}
DATA_DIR = Path("/data")


def main():
    started = time.perf_counter()
    DAILY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    output = DATA_DIR / f"eligible_symbols_{today}.csv"

    if output.exists() and output.stat().st_size > 0:
        cached = pd.read_csv(output)
        if "symbol" in cached.columns and len(cached) > 0:
            print(f"[{now_label()}] Eligibility cache already current: {output} ({len(cached)} symbols)", flush=True)
            return 0

    symbols = [symbol for symbol in load_symbols() if symbol not in BAD_TICKERS]

    print(f"[{now_label()}] Building eligibility universe from {len(symbols)} symbols", flush=True)
    today_ts = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    refreshed, missing_bad = refresh_daily_cache_batch(
        symbols, today=today_ts, batch_size=BATCH_SIZE
    )

    rows = []
    liquidity_failed = 0
    longterm_failed = 0

    for index, symbol in enumerate(symbols, start=1):
        liquidity = compute_liquidity_features(load_daily_volume(symbol))
        features = compute_longterm_features(load_daily_close(symbol))

        if not liquidity.get("pass_liquidity"):
            liquidity_failed += 1
        elif features is None or not features.get("pass_longterm"):
            longterm_failed += 1
        else:
            rows.append({"symbol": symbol, **liquidity, **features})

        if index % 500 == 0:
            print(f"[{now_label()}] Eligibility scan progress: {index}/{len(symbols)}", flush=True)

    if not rows:
        raise RuntimeError("Eligibility refresh produced zero eligible symbols; refusing to overwrite cache")

    frame = pd.DataFrame(rows)
    tmp = output.with_suffix(".csv.tmp")
    frame.to_csv(tmp, index=False)
    tmp.replace(output)

    print(
        f"[{now_label()}] Saved {output} | eligible={len(frame)} | "
        f"liquidity_failed={liquidity_failed} | longterm_failed={longterm_failed} | "
        f"daily_refreshed={refreshed} | daily_missing_bad={missing_bad} | "
        f"elapsed={time.perf_counter() - started:.1f}s",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
