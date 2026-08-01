#!/usr/bin/env python3
"""
trendline_scanner_v22.py
VERSION: 2026-05-10-live-cycle-speed-test-v22

Purpose:
    Live paper-watcher skeleton for the flash-dip strategy.

    This version is intentionally SAFE:
        - does NOT place real trades
        - does NOT place paper trades yet
        - runs ONE scan cycle by default
        - prints how long each phase takes

    Goal:
        Test whether a live scan cycle can run fast enough.

Logic:
    1. Load cached daily history.
    2. Filter long-term uptrend symbols.
    3. Download latest 1-minute intraday bars from Yahoo.
    4. Detect:
        - long-term uptrend
        - pre-crash intraday uptrend
        - recent flash drop
    5. Print candidates.
    6. Print timing.

Run:
    cd ~/Desktop
    source scannerenv/bin/activate
    python3 trendline_scanner_v22.py

Notes:
    - After hours, Yahoo may still return today's/latest intraday bars.
    - This is mainly for speed testing.
"""

from __future__ import annotations

import math
import time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf


INPUT_FILE = Path("./1Mvolumesymbols.csv")
DAILY_CACHE_DIR = Path("./cache")
OUTPUT_DIR = Path("./runtime")

MAX_SYMBOLS_TO_SCAN = None

# For speed testing. Increase/decrease.
BATCH_SIZE = 25

INTRADAY_PERIOD = "1d"
INTRADAY_INTERVAL = "1m"

NEW_YORK_TZ = ZoneInfo("America/New_York")
MARKET_OPEN = dtime(9, 30)
MARKET_CLOSE = dtime(16, 0)

# Long-term filter.
MIN_6M_SLOPE_PCT_PER_DAY = 0.05
MIN_R2_6M = 0.30
MAX_ANNUALIZED_VOLATILITY_PCT = 120.0

# Flash setup.
PRE_CRASH_TREND_MINUTES = 30
MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR = 0.50
MIN_PRE_CRASH_RETURN_PCT = 0.25

FLASH_WINDOW_MINUTES = 3
FLASH_DROP_PCT = 2.0
MAX_FLASH_DROP_PCT = 12.0

# Broad filter.
MAX_FLASHING_FRACTION = 0.10


def now_label() -> str:
    return datetime.now().strftime("%H:%M:%S")


def is_us_regular_market_open() -> bool:
    now_ny = datetime.now(NEW_YORK_TZ)
    if now_ny.weekday() >= 5:
        return False
    return MARKET_OPEN <= now_ny.time() <= MARKET_CLOSE


def clean_symbol(symbol):
    if pd.isna(symbol):
        return None
    s = str(symbol).strip().upper()
    if not s or s in {"NAN", "NONE"}:
        return None
    return s.replace(".", "-")


def safe_symbol(symbol):
    return symbol.replace("/", "_").replace("\\", "_").replace(":", "_")


def daily_cache_file(symbol):
    return DAILY_CACHE_DIR / f"daily_6mo_{safe_symbol(symbol)}.csv"


def load_symbols():
    df = pd.read_csv(INPUT_FILE)

    for col in ["Ticker", "ticker", "Symbol", "symbol"]:
        if col in df.columns:
            symbols = [clean_symbol(x) for x in df[col].tolist()]
            symbols = [s for s in symbols if s]
            symbols = list(dict.fromkeys(symbols))
            if MAX_SYMBOLS_TO_SCAN is not None:
                symbols = symbols[:MAX_SYMBOLS_TO_SCAN]
            return symbols

    raise ValueError(f"No ticker column found. Columns: {list(df.columns)}")


def load_daily_close(symbol):
    path = daily_cache_file(symbol)

    if not path.exists():
        return None

    try:
        df = pd.read_csv(path)
    except Exception:
        return None

    if "Date" not in df.columns or "Close" not in df.columns:
        return None

    idx = pd.to_datetime(df["Date"], errors="coerce")
    vals = pd.to_numeric(df["Close"], errors="coerce")

    s = pd.Series(vals.values, index=idx)
    s = s.dropna()
    s = s[s > 0]
    s = s.sort_index()

    return s if len(s) else None



def refresh_daily_cache_for_symbol(symbol):
    """
    Ensure one symbol has usable 6-month daily cache.
    Missing cache: download 6mo.
    Existing cache: if latest date is stale, re-download compact 6mo snapshot.
    This is simple, safe, and avoids downloading everything every scan once warm.
    """
    path = daily_cache_file(symbol)

    existing = load_daily_close(symbol)
    today = pd.Timestamp.now('UTC').tz_localize(None).normalize()

    if existing is not None and len(existing) >= 60:
        last_date = pd.Timestamp(existing.index.max()).tz_localize(None).normalize()
        # Allow 1-day tolerance for weekends/holidays/timezone weirdness.
        if (today - last_date).days <= 1:
            return False

    try:
        df = yf.download(
            tickers=symbol,
            period="6mo",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
            timeout=20,
        )
    except Exception:
        return False

    if df is None or df.empty:
        return False

    # yfinance sometimes returns MultiIndex columns even for one ticker.
    if isinstance(df.columns, pd.MultiIndex):
        if ("Close", symbol) in df.columns:
            close = df[("Close", symbol)]
        elif "Close" in df.columns.get_level_values(0):
            close = df.xs("Close", level=0, axis=1).iloc[:, 0]
        else:
            return False
    else:
        if "Close" not in df.columns:
            return False
        close = df["Close"]

    out = pd.DataFrame({
        "Date": pd.to_datetime(close.index).date,
        "Close": pd.to_numeric(close.values, errors="coerce"),
    }).dropna()

    if len(out) < 60:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return True

def fit_log_slope_pct_per_unit(prices, periods_per_unit):
    prices = prices.dropna()
    prices = prices[prices > 0]

    if len(prices) < 5:
        return math.nan, math.nan

    y = np.log(prices.to_numpy(dtype=float))
    x = np.arange(len(y), dtype=float) / periods_per_unit

    try:
        slope, intercept = np.polyfit(x, y, 1)
    except Exception:
        return math.nan, math.nan

    y_hat = slope * x + intercept
    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)

    r2 = math.nan if ss_tot == 0 else 1 - (ss_res / ss_tot)
    slope_pct = (math.exp(slope) - 1) * 100

    return float(slope_pct), float(r2)


def compute_longterm_features(close):
    if close is None or len(close) < 60:
        return None

    slope, r2 = fit_log_slope_pct_per_unit(close, periods_per_unit=1.0)

    daily_returns = close.pct_change().dropna()
    if len(daily_returns) < 5:
        vol = math.nan
    else:
        vol = float(daily_returns.std() * math.sqrt(252) * 100)

    pass_longterm = (
        not math.isnan(slope)
        and not math.isnan(r2)
        and not math.isnan(vol)
        and slope >= MIN_6M_SLOPE_PCT_PER_DAY
        and r2 >= MIN_R2_6M
        and vol <= MAX_ANNUALIZED_VOLATILITY_PCT
    )

    return {
        "longterm_slope_6m_pct_per_day": slope,
        "longterm_r2_6m": r2,
        "volatility_6m_annualized_pct": vol,
        "pass_longterm": pass_longterm,
    }


def chunk_list(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def download_intraday_batch(symbols):
    return yf.download(
        tickers=symbols,
        period=INTRADAY_PERIOD,
        interval=INTRADAY_INTERVAL,
        group_by="column",
        auto_adjust=False,
        prepost=False,
        threads=False,
        progress=False,
        timeout=20,
    )


def get_series(data, symbol, field):
    if data.empty:
        return None

    try:
        if isinstance(data.columns, pd.MultiIndex):
            if (field, symbol) in data.columns:
                return data[(field, symbol)].dropna()
            if (symbol, field) in data.columns:
                return data[(symbol, field)].dropna()
            return None

        if field in data.columns:
            return data[field].dropna()

    except Exception:
        return None

    return None


def detect_latest_flash(symbol, intraday_close, features):
    """
    Detect only the latest possible flash setup for this symbol.
    This is what a live watcher cares about.
    """
    if intraday_close is None or intraday_close.empty:
        return None

    s = intraday_close.dropna()
    s = s[s > 0]
    s = s.sort_index()

    needed = PRE_CRASH_TREND_MINUTES + FLASH_WINDOW_MINUTES + 1
    if len(s) < needed:
        return None

    flash = s.iloc[-FLASH_WINDOW_MINUTES:]
    pre = s.iloc[-(PRE_CRASH_TREND_MINUTES + FLASH_WINDOW_MINUTES):-FLASH_WINDOW_MINUTES]

    if len(pre) < 5 or len(flash) < 2:
        return None

    pre_start = float(pre.iloc[0])
    pre_end = float(pre.iloc[-1])
    flash_start = float(flash.iloc[0])
    flash_end = float(flash.iloc[-1])

    if pre_start <= 0 or flash_start <= 0 or flash_end <= 0:
        return None

    pre_return_pct = ((pre_end / pre_start) - 1) * 100
    pre_slope_pct_per_hour, pre_r2 = fit_log_slope_pct_per_unit(pre, periods_per_unit=60.0)
    flash_drop_pct = ((flash_start - flash_end) / flash_start) * 100

    pass_pre_return = pre_return_pct >= MIN_PRE_CRASH_RETURN_PCT
    pass_pre_slope = (
        not math.isnan(pre_slope_pct_per_hour)
        and pre_slope_pct_per_hour >= MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR
    )
    pass_flash = (
        not math.isnan(flash_drop_pct)
        and flash_drop_pct >= FLASH_DROP_PCT
        and flash_drop_pct <= MAX_FLASH_DROP_PCT
    )

    if not (pass_pre_return and pass_pre_slope and pass_flash):
        return None

    entry_price = flash_end
    target_price = entry_price + 0.60 * (flash_start - entry_price)
    stop_price = entry_price * 0.95

    return {
        "symbol": symbol,
        "detected_at": str(s.index[-1]),
        "entry_price": entry_price,
        "flash_start_price": flash_start,
        "flash_drop_pct": flash_drop_pct,
        "pre_crash_return_pct": pre_return_pct,
        "pre_crash_slope_pct_per_hour": pre_slope_pct_per_hour,
        "pre_crash_r2": pre_r2,
        "target_price": target_price,
        "stop_price": stop_price,
        **features,
    }


def main():
    DAILY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cycle_start = time.perf_counter()

    print(f"trendline_scanner_v22.py started at {now_label()}")
    print(f"US regular market open now: {is_us_regular_market_open()}")
    print("Running ONE scan cycle for speed testing.\n")

    # Phase 1: load symbols.
    t0 = time.perf_counter()
    symbols = load_symbols()
    t1 = time.perf_counter()
    print(f"[{now_label()}] Loaded {len(symbols)} symbols in {t1 - t0:.2f}s")

    # Phase 2: refresh/load daily cache and long-term filter.
    t0 = time.perf_counter()
    eligible = []
    features_by_symbol = {}
    refreshed = 0
    missing_or_bad = 0

    for n, symbol in enumerate(symbols, start=1):
        if refresh_daily_cache_for_symbol(symbol):
            refreshed += 1

        close = load_daily_close(symbol)
        if close is None:
            missing_or_bad += 1

        features = compute_longterm_features(close)

        if features is not None and features["pass_longterm"]:
            eligible.append(symbol)
            features_by_symbol[symbol] = features

        if n % 500 == 0:
            print(f"  long-term scan progress: {n}/{len(symbols)}")

    t1 = time.perf_counter()
    print(f"[{now_label()}] Daily cache refreshed/created: {refreshed}")
    print(f"[{now_label()}] Daily cache missing/bad after refresh: {missing_or_bad}")
    print(f"[{now_label()}] Long-term eligible: {len(eligible)} in {t1 - t0:.2f}s")

    # Phase 3: download intraday and detect latest flash.
    t0 = time.perf_counter()
    candidates = []
    batches = list(chunk_list(eligible, BATCH_SIZE))
    failed_batches = 0

    print(f"[{now_label()}] Downloading 1m intraday data in {len(batches)} batches of {BATCH_SIZE}...")

    for batch_num, batch_symbols in enumerate(batches, start=1):
        batch_start = time.perf_counter()

        try:
            intraday = download_intraday_batch(batch_symbols)
        except Exception as e:
            failed_batches += 1
            print(f"  Batch {batch_num}/{len(batches)} failed: {e}")
            intraday = pd.DataFrame()

        batch_candidates = 0

        for symbol in batch_symbols:
            close = get_series(intraday, symbol, "Close")
            event = detect_latest_flash(
                symbol=symbol,
                intraday_close=close,
                features=features_by_symbol[symbol],
            )

            if event is not None:
                candidates.append(event)
                batch_candidates += 1

        batch_elapsed = time.perf_counter() - batch_start

        if batch_num == 1 or batch_num % 5 == 0 or batch_num == len(batches):
            pct = (batch_num / len(batches)) * 100 if batches else 100
            print(
                f"  intraday batch {batch_num}/{len(batches)} "
                f"({pct:.1f}%) | {batch_elapsed:.2f}s | "
                f"new candidates: {batch_candidates} | total: {len(candidates)}"
            )

    t1 = time.perf_counter()
    print(f"[{now_label()}] Intraday download+detection completed in {t1 - t0:.2f}s")
    print(f"Failed batches: {failed_batches}")

    # Phase 4: broad simultaneous flashing check.
    flashing_fraction = len(candidates) / len(eligible) if eligible else 0
    broad_block = flashing_fraction >= MAX_FLASHING_FRACTION

    print("\n===== LIVE CYCLE RESULT =====")
    print(f"Eligible symbols scanned: {len(eligible)}")
    print(f"Candidates found: {len(candidates)}")
    print(f"Flashing fraction: {flashing_fraction:.2%}")
    print(f"Broad block triggered: {broad_block}")

    if candidates:
        out = pd.DataFrame(candidates)
        out = out.sort_values(by=["flash_drop_pct", "pre_crash_slope_pct_per_hour"], ascending=[False, False])
        print("\nCandidates:")
        print(out.head(20).to_string(index=False))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = OUTPUT_DIR / f"live_cycle_candidates_{timestamp}.csv"
        out.to_csv(output_file, index=False)
        print(f"\nSaved candidates to: {output_file}")

    cycle_elapsed = time.perf_counter() - cycle_start

    print("\n===== TIMING SUMMARY =====")
    print(f"Total one-cycle runtime: {cycle_elapsed:.2f}s")
    print(f"Approx max cycles per minute: {60 / cycle_elapsed:.2f}" if cycle_elapsed > 0 else "n/a")

    print("\nNote: this is still using Yahoo 1m downloads. A broker/Polygon/WebSocket feed could be faster.")


if __name__ == "__main__":
    main()
