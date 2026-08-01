#!/usr/bin/env python3
"""
trendline_scanner_v14.py
VERSION: 2026-05-09-intraday-cache-v14

Purpose:
    Historical intraday replay for the ACTUAL intended strategy:

    1. Long-term uptrend filter:
        - 6-month slope positive
        - trend quality acceptable

    2. Intraday setup:
        - before the crash, stock was trending up intraday
        - then a sudden flash drop occurs over a short window

    3. Entry:
        - enter at the end of the flash-drop window

    4. Exit:
        - target = recover 60% of flash drop
        - stop = 5% below entry
        - if neither hits by end of day, exit at final available intraday close

Data:
    - Long-term daily history comes from your cache:
        ~/Desktop/trendline_cache/

    - Intraday 1-minute data is pulled from Yahoo for recent days.
      Yahoo generally only provides recent 1-minute history.

Output:
    ~/Desktop/intraday_replay_YYYYMMDD_HHMMSS.csv

Run:
    cd ~/Desktop
    source scannerenv/bin/activate
    python3 trendline_scanner_v14.py
"""

from __future__ import annotations

import math
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


INPUT_FILE = Path("1Mvolumesymbols.csv")
CACHE_DIR = Path("trendline_cache")
INTRADAY_CACHE_DIR = Path("trendline_intraday_cache")
OUTPUT_DIR = Path.home() / "Desktop"

# Start with full list. If too slow, set to e.g. 300.
MAX_SYMBOLS_TO_SCAN = None
BATCH_SIZE = 10

INTRADAY_PERIOD = "5d"
INTRADAY_INTERVAL = "1m"

# Long-term filter.
MIN_6M_SLOPE_PCT_PER_DAY = 0.05
MIN_R2_6M = 0.30
MAX_ANNUALIZED_VOLATILITY_PCT = 120.0

# Setup definition.
PRE_CRASH_TREND_MINUTES = 30
MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR = 0.50
MIN_PRE_CRASH_RETURN_PCT = 0.25

FLASH_WINDOW_MINUTES = 3
FLASH_DROP_PCT = 2.0
MAX_FLASH_DROP_PCT = 12.0

# Avoid too many overlapping entries per symbol per day.
MAX_TRADES_PER_SYMBOL_PER_DAY = 1

# Exit settings.
RECOVERY_TARGET_FRACTION = 0.60
STOP_LOSS_FRACTION_BELOW_ENTRY = 0.05
PAPER_TRADE_DOLLARS = 2000.0


def clean_symbol(symbol):
    if pd.isna(symbol):
        return None
    s = str(symbol).strip().upper()
    if not s or s in {"NAN", "NONE"}:
        return None
    return s.replace(".", "-")


def safe_filename_symbol(symbol):
    return symbol.replace("/", "_").replace("\\", "_").replace(":", "_")


def cache_file_for(symbol):
    return CACHE_DIR / f"daily_6mo_{safe_filename_symbol(symbol)}.csv"


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


def load_daily_close_from_cache(symbol):
    path = cache_file_for(symbol)
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


def longterm_metrics(close):
    if close is None or len(close) < 60:
        return None

    slope, r2 = fit_log_slope_pct_per_unit(close, periods_per_unit=1.0)

    daily_returns = close.pct_change().dropna()
    if len(daily_returns) < 5:
        vol = math.nan
    else:
        vol = float(daily_returns.std() * math.sqrt(252) * 100)

    return {
        "longterm_slope_6m_pct_per_day": slope,
        "longterm_r2_6m": r2,
        "volatility_6m_annualized_pct": vol,
        "pass_longterm": (
            not math.isnan(slope)
            and not math.isnan(r2)
            and not math.isnan(vol)
            and slope >= MIN_6M_SLOPE_PCT_PER_DAY
            and r2 >= MIN_R2_6M
            and vol <= MAX_ANNUALIZED_VOLATILITY_PCT
        ),
    }


def chunk_list(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def intraday_cache_file_for(symbol):
    INTRADAY_CACHE_DIR.mkdir(exist_ok=True)
    safe = symbol.replace("/", "_").replace("\\", "_").replace(":", "_")
    return INTRADAY_CACHE_DIR / f"intraday_1m_5d_{safe}.csv"


def intraday_cache_is_fresh(path):
    """
    Treat intraday cache as fresh if it was written today.
    This is fine for weekend threshold experiments.
    """
    if not path.exists():
        return False
    modified_day = datetime.fromtimestamp(path.stat().st_mtime).date()
    return modified_day == datetime.now().date()


def load_intraday_cache(symbol):
    path = intraday_cache_file_for(symbol)
    if not intraday_cache_is_fresh(path):
        return None

    try:
        df = pd.read_csv(path)
    except Exception:
        return None

    if "Datetime" not in df.columns or "Close" not in df.columns:
        return None

    s = pd.Series(
        pd.to_numeric(df["Close"], errors="coerce").values,
        index=pd.to_datetime(df["Datetime"], errors="coerce"),
    )

    s = s.dropna()
    s = s[s > 0]
    s = s.sort_index()

    return s if len(s) else None


def save_intraday_cache(symbol, close_series):
    path = intraday_cache_file_for(symbol)

    if close_series is None or len(close_series) == 0:
        return

    s = normalize_intraday_index(close_series)

    if s.empty:
        return

    out = pd.DataFrame({
        "Datetime": pd.to_datetime(s.index).astype(str),
        "Close": s.values,
    })

    out.to_csv(path, index=False)


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
        timeout=30,
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


def normalize_intraday_index(series):
    s = series.dropna()
    s = s[s > 0]
    s.index = pd.to_datetime(s.index, errors="coerce")
    s = s[~s.index.isna()]
    return s.sort_index()


def simulate_exit(day_prices, entry_idx, entry_price, flash_start_price):
    target_price = entry_price + RECOVERY_TARGET_FRACTION * (flash_start_price - entry_price)
    stop_price = entry_price * (1 - STOP_LOSS_FRACTION_BELOW_ENTRY)

    for j in range(entry_idx + 1, len(day_prices)):
        px = float(day_prices.iloc[j])
        ts = day_prices.index[j]

        if px >= target_price:
            ret = ((target_price / entry_price) - 1) * 100
            return {
                "exit_time": str(ts),
                "exit_price": target_price,
                "outcome": "hit_target",
                "trade_return_pct": ret,
                "paper_pnl_dollars": (ret / 100) * PAPER_TRADE_DOLLARS,
                "target_price": target_price,
                "stop_price": stop_price,
            }

        if px <= stop_price:
            ret = ((stop_price / entry_price) - 1) * 100
            return {
                "exit_time": str(ts),
                "exit_price": stop_price,
                "outcome": "hit_stop",
                "trade_return_pct": ret,
                "paper_pnl_dollars": (ret / 100) * PAPER_TRADE_DOLLARS,
                "target_price": target_price,
                "stop_price": stop_price,
            }

    final_px = float(day_prices.iloc[-1])
    final_ts = day_prices.index[-1]
    ret = ((final_px / entry_price) - 1) * 100

    return {
        "exit_time": str(final_ts),
        "exit_price": final_px,
        "outcome": "exit_eod",
        "trade_return_pct": ret,
        "paper_pnl_dollars": (ret / 100) * PAPER_TRADE_DOLLARS,
        "target_price": target_price,
        "stop_price": stop_price,
    }


def find_trades_for_symbol(symbol, intraday_close, metrics):
    trades = []

    if intraday_close is None or intraday_close.empty:
        return trades

    s = normalize_intraday_index(intraday_close)

    if s.empty:
        return trades

    # Group by calendar day in the exchange timezone as Yahoo provides it.
    for day, day_prices in s.groupby(s.index.date):
        day_prices = day_prices.dropna()
        day_prices = day_prices[day_prices > 0]

        needed = PRE_CRASH_TREND_MINUTES + FLASH_WINDOW_MINUTES + 1
        if len(day_prices) < needed:
            continue

        trades_today = 0

        # i is the final candle index of the flash window / entry.
        for i in range(needed - 1, len(day_prices) - 1):
            flash = day_prices.iloc[i - FLASH_WINDOW_MINUTES + 1:i + 1]
            pre = day_prices.iloc[i - FLASH_WINDOW_MINUTES - PRE_CRASH_TREND_MINUTES + 1:i - FLASH_WINDOW_MINUTES + 1]

            if len(pre) < 5 or len(flash) < 2:
                continue

            pre_start = float(pre.iloc[0])
            pre_end = float(pre.iloc[-1])
            flash_start = float(flash.iloc[0])
            flash_end = float(flash.iloc[-1])

            pre_return_pct = ((pre_end / pre_start) - 1) * 100 if pre_start > 0 else math.nan
            pre_slope_pct_per_hour, pre_r2 = fit_log_slope_pct_per_unit(pre, periods_per_unit=60.0)

            flash_drop_pct = ((flash_start - flash_end) / flash_start) * 100 if flash_start > 0 else math.nan

            pass_pre_slope = not math.isnan(pre_slope_pct_per_hour) and pre_slope_pct_per_hour >= MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR
            pass_pre_return = not math.isnan(pre_return_pct) and pre_return_pct >= MIN_PRE_CRASH_RETURN_PCT
            pass_flash = not math.isnan(flash_drop_pct) and flash_drop_pct >= FLASH_DROP_PCT and flash_drop_pct <= MAX_FLASH_DROP_PCT

            # Flexible-score research mode:
            # Keep "near-enough" candidates, not only strict v14 passes.
            # Lower miss_score = closer to the original v14 trigger.
            flash_penalty = max(0.0, FLASH_DROP_PCT - flash_drop_pct) / max(FLASH_DROP_PCT, 1e-9) if not math.isnan(flash_drop_pct) else 999
            pre_ret_penalty = max(0.0, MIN_PRE_CRASH_RETURN_PCT - pre_return_pct) / max(MIN_PRE_CRASH_RETURN_PCT, 1e-9) if not math.isnan(pre_return_pct) else 999
            pre_slope_penalty = max(0.0, MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR - pre_slope_pct_per_hour) / max(MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR, 1e-9) if not math.isnan(pre_slope_pct_per_hour) else 999

            miss_score = flash_penalty + pre_ret_penalty + pre_slope_penalty

            # Quality-style score where higher can be interpreted as stronger raw setup.
            # This lets us later ask whether excellent trend quality can compensate for smaller drops.
            quality_score = (
                max(0.0, flash_drop_pct / max(FLASH_DROP_PCT, 1e-9)) +
                max(0.0, pre_return_pct / max(MIN_PRE_CRASH_RETURN_PCT, 1e-9)) +
                max(0.0, pre_slope_pct_per_hour / max(MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR, 1e-9)) +
                max(0.0, pre_r2)
            )

            strict_v14_pass = pass_pre_slope and pass_pre_return and pass_flash

            # Candidate universe for research:
            # keep setups that have at least some flash dip or strong trend context.
            if not (
                strict_v14_pass
                or miss_score <= 2.0
                or flash_drop_pct >= 1.0
                or (pre_return_pct >= MIN_PRE_CRASH_RETURN_PCT and pre_slope_pct_per_hour >= MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR)
            ):
                continue

            entry_price = flash_end
            entry_time = day_prices.index[i]

            exit_sim = simulate_exit(
                day_prices=day_prices,
                entry_idx=i,
                entry_price=entry_price,
                flash_start_price=flash_start,
            )

            trades.append({
                "symbol": symbol,
                "trade_date": str(day),
                "entry_time": str(entry_time),
                "entry_price": entry_price,
                "flash_start_price": flash_start,
                "flash_drop_pct": flash_drop_pct,
                "pre_crash_return_pct": pre_return_pct,
                "pre_crash_slope_pct_per_hour": pre_slope_pct_per_hour,
                "pre_crash_r2": pre_r2,
                "pass_flash": pass_flash,
                "pass_pre_return": pass_pre_return,
                "pass_pre_slope": pass_pre_slope,
                "strict_v14_pass": strict_v14_pass,
                "flash_penalty": flash_penalty,
                "pre_ret_penalty": pre_ret_penalty,
                "pre_slope_penalty": pre_slope_penalty,
                "miss_score": miss_score,
                "quality_score": quality_score,
                "target_price": exit_sim["target_price"],
                "stop_price": exit_sim["stop_price"],
                "exit_time": exit_sim["exit_time"],
                "exit_price": exit_sim["exit_price"],
                "outcome": exit_sim["outcome"],
                "trade_return_pct": exit_sim["trade_return_pct"],
                "paper_pnl_dollars": exit_sim["paper_pnl_dollars"],
                **metrics,
            })

            trades_today += 1
            if trades_today >= MAX_TRADES_PER_SYMBOL_PER_DAY:
                break

    return trades


def main():
    symbols = load_symbols()
    print(f"Loaded {len(symbols)} symbols")
    print("Loading long-term cache and filtering symbols...")

    eligible_symbols = []
    metrics_by_symbol = {}

    for n, symbol in enumerate(symbols, start=1):
        close = load_daily_close_from_cache(symbol)
        metrics = longterm_metrics(close)
        if metrics is not None and metrics["pass_longterm"]:
            eligible_symbols.append(symbol)
            metrics_by_symbol[symbol] = metrics

    print(f"Eligible by long-term filter: {len(eligible_symbols)}")
    print(f"Intraday cache directory: {INTRADAY_CACHE_DIR}")
    print("Using cached 1-minute data where available; downloading missing/fresh-needed symbols.\n")

    all_trades = []

    cached_intraday_by_symbol = {}
    missing_intraday_symbols = []

    for symbol in eligible_symbols:
        cached = load_intraday_cache(symbol)
        if cached is not None and len(cached) > 0:
            cached_intraday_by_symbol[symbol] = cached
        else:
            missing_intraday_symbols.append(symbol)

    print(f"Intraday cache hits: {len(cached_intraday_by_symbol)}")
    print(f"Intraday downloads needed: {len(missing_intraday_symbols)}")

    # First process cached symbols.
    print("\nProcessing cached intraday data...")
    for n, symbol in enumerate(cached_intraday_by_symbol.keys(), start=1):
        if n % 250 == 0:
            print(f"  Cached processed {n}/{len(cached_intraday_by_symbol)}")

        trades = find_trades_for_symbol(
            symbol=symbol,
            intraday_close=cached_intraday_by_symbol[symbol],
            metrics=metrics_by_symbol[symbol],
        )
        all_trades.extend(trades)

    # Then download missing symbols and immediately cache them.
    batches = list(chunk_list(missing_intraday_symbols, BATCH_SIZE))

    for batch_num, batch_symbols in enumerate(batches, start=1):
        print(f"Download intraday batch {batch_num}/{len(batches)}: {batch_symbols}")

        try:
            intraday = download_intraday_batch(batch_symbols)
        except Exception as e:
            print(f"  Intraday download failed: {e}")
            intraday = pd.DataFrame()

        for symbol in batch_symbols:
            close = get_series(intraday, symbol, "Close")

            if close is not None and len(close) > 0:
                save_intraday_cache(symbol, close)

            trades = find_trades_for_symbol(
                symbol=symbol,
                intraday_close=close,
                metrics=metrics_by_symbol[symbol],
            )
            all_trades.extend(trades)

        time.sleep(0.1)

    df = pd.DataFrame(all_trades)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"flexible_score_replay_{timestamp}.csv"

    if df.empty:
        print("\nNo historical intraday flash-crash trades found.")
        print("Try loosening FLASH_DROP_PCT, PRE_CRASH filters, or check if Yahoo returned 1m data.")
        return

    df = df.sort_values(by="paper_pnl_dollars", ascending=False)
    df.to_csv(output_file, index=False)

    total_pnl = float(df["paper_pnl_dollars"].sum())
    avg_pnl = float(df["paper_pnl_dollars"].mean())
    median_pnl = float(df["paper_pnl_dollars"].median())
    avg_return = float(df["trade_return_pct"].mean())
    median_return = float(df["trade_return_pct"].median())
    win_rate = float((df["trade_return_pct"] > 0).mean() * 100)

    print("\n===== HISTORICAL INTRADAY REPLAY SUMMARY =====")
    print(f"Trades found: {len(df)}")
    print(f"Total simulated P/L: ${total_pnl:,.2f}")
    print(f"Average P/L per trade: ${avg_pnl:,.2f}")
    print(f"Median P/L per trade: ${median_pnl:,.2f}")
    print(f"Average return per trade: {avg_return:.2f}%")
    print(f"Median return per trade: {median_return:.2f}%")
    print(f"Win rate: {win_rate:.2f}%")

    print("\nOutcome counts:")
    print(df["outcome"].value_counts())

    print(f"\nSaved detailed results to:\n{output_file}")

    cols = [
        "symbol",
        "trade_date",
        "entry_time",
        "entry_price",
        "flash_drop_pct",
        "pre_crash_return_pct",
        "pre_crash_slope_pct_per_hour",
        "target_price",
        "stop_price",
        "outcome",
        "trade_return_pct",
        "paper_pnl_dollars",
        "longterm_slope_6m_pct_per_day",
        "longterm_r2_6m",
        "volatility_6m_annualized_pct",
    ]

    print("\nTop trades:")
    print(df[cols].head(30).to_string(index=False))


if __name__ == "__main__":
    main()
