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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf
import os
from collections import defaultdict, deque
from schwab.auth import client_from_token_file


INPUT_FILE = Path("/app/1Mvolumesymbols.csv")
DAILY_CACHE_DIR = Path("/data/trendline_cache")
BAD_SYMBOLS_FILE = Path("/data/bad_symbols.txt")
OUTPUT_DIR = Path("/app")
TOKEN_PATH = Path("/data/schwab_token.json")
SCHWAB_APP_KEY = os.getenv("SCHWAB_APP_KEY")
SCHWAB_SECRET = os.getenv("SCHWAB_SECRET", "")

MAX_SYMBOLS_TO_SCAN = None

# For speed testing. Increase/decrease.
BATCH_SIZE = 75
QUOTE_BATCH_SIZE = 500
LIVE_POLL_SECONDS = 5
LIVE_MAX_CYCLES = 20
ROLLING_MINUTES_TO_KEEP = 90

INTRADAY_PERIOD = "1d"
INTRADAY_INTERVAL = "1m"

NEW_YORK_TZ = ZoneInfo("America/New_York")
MARKET_OPEN = dtime(9, 30)
MARKET_CLOSE = dtime(16, 0)

# Long-term filter.
MIN_6M_SLOPE_PCT_PER_DAY = 0.05
MIN_R2_6M = 0.30
MAX_ANNUALIZED_VOLATILITY_PCT = 120.0

# Liquidity filter: every one of the latest 5 completed trading days must
# have at least 1,000,000 shares traded.
LIQUIDITY_LOOKBACK_DAYS = 5
MIN_DAILY_VOLUME = 1_000_000

# Flash setup.
PRE_CRASH_TREND_MINUTES = 30
MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR = 0.50
MIN_PRE_CRASH_RETURN_PCT = 0.25

FLASH_WINDOW_MINUTES = 3
FLASH_DROP_PCT = 2.0
MAX_FLASH_DROP_PCT = 12.0

# Broad filter.
MAX_FLASHING_FRACTION = 0.10



def load_bad_symbols():
    if not BAD_SYMBOLS_FILE.exists():
        return set()
    return {x.strip().upper() for x in BAD_SYMBOLS_FILE.read_text().splitlines() if x.strip()}


def save_bad_symbols(symbols):
    BAD_SYMBOLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    BAD_SYMBOLS_FILE.write_text("\n".join(sorted(set(symbols))) + "\n")


def mark_bad_symbols(symbols, reason="bad data"):
    if not symbols:
        return
    bad = load_bad_symbols()
    before = len(bad)
    bad.update(s.upper() for s in symbols if s)
    save_bad_symbols(bad)
    added = len(bad) - before
    if added:
        print(f"[{now_label()}] Marked {added} bad symbols ({reason})")

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


def load_daily_history(symbol):
    """Load cached daily Date/Close/Volume history for one symbol."""
    path = daily_cache_file(symbol)

    if not path.exists():
        return None

    try:
        df = pd.read_csv(path)
    except Exception:
        return None

    if "Date" not in df.columns or "Close" not in df.columns:
        return None

    out = pd.DataFrame({
        "Date": pd.to_datetime(df["Date"], errors="coerce"),
        "Close": pd.to_numeric(df["Close"], errors="coerce"),
    })
    if "Volume" in df.columns:
        out["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
    else:
        out["Volume"] = np.nan

    out = out.dropna(subset=["Date", "Close"])
    out = out[out["Close"] > 0]
    out = out.sort_values("Date").drop_duplicates("Date", keep="last")
    out = out.set_index("Date")
    return out if len(out) else None


def load_daily_close(symbol):
    history = load_daily_history(symbol)
    if history is None:
        return None
    close = history["Close"].dropna()
    return close if len(close) else None


def load_daily_volume(symbol):
    history = load_daily_history(symbol)
    if history is None or "Volume" not in history.columns:
        return None
    volume = pd.to_numeric(history["Volume"], errors="coerce").dropna()
    volume = volume[volume >= 0]
    return volume if len(volume) else None


def compute_liquidity_features(volume):
    """Require all latest 5 completed trading days to trade >= 1M shares."""
    if volume is None:
        recent = pd.Series(dtype=float)
    else:
        recent = pd.to_numeric(pd.Series(volume), errors="coerce").dropna().tail(LIQUIDITY_LOOKBACK_DAYS)

    pass_liquidity = (
        len(recent) == LIQUIDITY_LOOKBACK_DAYS
        and bool((recent >= MIN_DAILY_VOLUME).all())
    )

    values = [int(v) for v in recent.tolist()]
    return {
        "liquidity_lookback_days": LIQUIDITY_LOOKBACK_DAYS,
        "min_daily_volume_required": MIN_DAILY_VOLUME,
        "last5_daily_volumes": ";".join(str(v) for v in values),
        "min_volume_last5": min(values) if values else math.nan,
        "pass_liquidity": pass_liquidity,
    }



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

    close = get_series(df, symbol, "Close")
    volume = get_series(df, symbol, "Volume")
    if close is None or close.empty or volume is None or volume.empty:
        return False

    joined = pd.concat([
        pd.to_numeric(close, errors="coerce").rename("Close"),
        pd.to_numeric(volume, errors="coerce").rename("Volume"),
    ], axis=1)
    out = joined.reset_index()
    out.columns = ["Date", "Close", "Volume"]
    out["Date"] = pd.to_datetime(out["Date"]).dt.date
    out = out.dropna(subset=["Date", "Close", "Volume"])

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



def cache_is_fresh(symbol, today=None):
    if today is None:
        today = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    history = load_daily_history(symbol)
    if history is None or len(history) < 60:
        return False
    # Old Close-only caches are deliberately stale so Volume gets populated.
    if "Volume" not in history.columns or history["Volume"].dropna().shape[0] < LIQUIDITY_LOOKBACK_DAYS:
        return False
    try:
        last_date = pd.Timestamp(history.index.max()).tz_localize(None).normalize()
    except Exception:
        return False
    return (today - last_date).days <= 1



def save_daily_cache(symbol, close, volume=None):
    """Save daily Close and Volume while preserving the existing public API."""
    if close is None:
        return False

    if isinstance(close, pd.DataFrame):
        if close.empty:
            return False
        if "Close" in close.columns:
            if volume is None and "Volume" in close.columns:
                volume = close["Volume"]
            close = close["Close"]
        else:
            close = close.iloc[:, 0]

    close = pd.to_numeric(pd.Series(close), errors="coerce")
    if volume is None:
        volume = pd.Series(np.nan, index=close.index)
    else:
        volume = pd.to_numeric(pd.Series(volume), errors="coerce")

    joined = pd.concat([close.rename("Close"), volume.rename("Volume")], axis=1)
    joined = joined[~joined.index.duplicated(keep="last")].sort_index()
    joined = joined[joined["Close"] > 0].tail(150)

    if joined["Close"].dropna().shape[0] < 60:
        return False

    out = joined.reset_index()
    out.columns = ["Date", "Close", "Volume"]
    out["Date"] = pd.to_datetime(out["Date"]).dt.date

    path = daily_cache_file(symbol)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    out.to_csv(tmp, index=False)
    tmp.replace(path)
    return True


def save_daily_close_cache(symbol, close):
    # Backward-compatible wrapper for any external callers.
    return save_daily_cache(symbol, close, volume=None)



def refresh_daily_cache_batch(symbols, today=None, batch_size=75):
    if today is None:
        today = pd.Timestamp.now("UTC").tz_localize(None).normalize()

    stale = [s for s in symbols if not cache_is_fresh(s, today=today)]
    print(f"[{now_label()}] Daily cache stale/missing: {len(stale)}")

    refreshed = 0
    for i, batch in enumerate(chunk_list(stale, batch_size), start=1):
        print(f"[{now_label()}] Refreshing daily batch {i}: {len(batch)} symbols")
        try:
            data = yf.download(
                tickers=batch,
                period="10d",
                interval="1d",
                group_by="column",
                auto_adjust=False,
                progress=False,
                threads=True,
                timeout=15,
            )
        except Exception as e:
            print(f"  daily batch failed: {e}")
            continue

        for symbol in batch:
            old = load_daily_history(symbol)
            new_close = get_series(data, symbol, "Close")
            new_volume = get_series(data, symbol, "Volume")

            if new_close is None or new_close.empty or new_volume is None or new_volume.empty:
                # Bootstrap fallback supplies a full Close history and recent Volume.
                try:
                    single = yf.download(
                        symbol,
                        period="6mo",
                        interval="1d",
                        auto_adjust=False,
                        progress=False,
                        threads=False,
                        timeout=10,
                    )
                    new_close = get_series(single, symbol, "Close")
                    new_volume = get_series(single, symbol, "Volume")
                except Exception:
                    new_close = None
                    new_volume = None

            if new_close is None or new_close.empty or new_volume is None or new_volume.empty:
                mark_bad_symbols([symbol], reason="no Yahoo daily Close/Volume data")
                continue

            new = pd.concat([
                pd.to_numeric(new_close, errors="coerce").rename("Close"),
                pd.to_numeric(new_volume, errors="coerce").rename("Volume"),
            ], axis=1)
            combined = new if old is None else pd.concat([old[["Close", "Volume"]], new])
            combined = combined[~combined.index.duplicated(keep="last")].sort_index().tail(150)

            if save_daily_cache(symbol, combined["Close"], combined["Volume"]):
                refreshed += 1

    missing_bad = sum(1 for s in symbols if load_daily_close(s) is None)
    return refreshed, missing_bad




def ensure_data_token():
    """
    Keep the live persistent token in /data updated.

    Weekly desktop refresh creates a fresh token in local schwab_token.json.
    fly deploy bundles that into /app/schwab_token.json.
    The bot reads /data/schwab_token.json.

    So on startup:
    - if /data token is missing/empty, copy /app -> /data
    - if /app token has newer creation_timestamp, copy /app -> /data
    """
    from pathlib import Path
    import shutil
    import json

    data_token = Path("/data/schwab_token.json")
    app_token = Path("/app/schwab_token.json")

    data_token.parent.mkdir(parents=True, exist_ok=True)

    if not app_token.exists() or app_token.stat().st_size == 0:
        print("ensure_data_token: no /app token found")
        return

    def token_created(path):
        try:
            obj = json.loads(path.read_text())
            return float(obj.get("creation_timestamp") or 0)
        except Exception:
            return 0.0

    if not data_token.exists() or data_token.stat().st_size == 0:
        shutil.copyfile(app_token, data_token)
        print("ensure_data_token: copied /app token to missing/empty /data token")
        return

    app_created = token_created(app_token)
    data_created = token_created(data_token)

    if app_created > data_created:
        shutil.copyfile(app_token, data_token)
        print(f"ensure_data_token: promoted newer token /app -> /data ({app_created} > {data_created})")
    else:
        print(f"ensure_data_token: /data token already current ({data_created} >= {app_created})")

def cleanup_quote_tapes(tapes_dir="/data/tapes", keep_newest=1, max_mb=300):
    """
    Prevent Fly volume from filling with intraday quote tapes.
    Keeps newest quote tape(s), then enforces size cap.
    Does not touch /data/trendline_cache.
    """
    from pathlib import Path

    d = Path(tapes_dir)
    d.mkdir(parents=True, exist_ok=True)

    files = sorted(d.glob("quotes_*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)

    for f in files[keep_newest:]:
        try:
            f.unlink()
        except Exception:
            pass

    files = sorted(d.glob("quotes_*.csv"), key=lambda f: f.stat().st_mtime)
    max_bytes = max_mb * 1024 * 1024
    total = sum(f.stat().st_size for f in files)

    for f in files:
        if total <= max_bytes:
            break
        try:
            size = f.stat().st_size
            f.unlink()
            total -= size
        except Exception:
            pass


def token_minutes_left(path):
    try:
        obj = json.loads(Path(path).read_text())
        token = obj.get("token", {}) if isinstance(obj.get("token"), dict) else obj
        expires = float(token.get("expires_at", 0) or obj.get("expires_at", 0) or 0)
        return (expires - time.time()) / 60 if expires else -999999
    except Exception:
        return -999999


def get_schwab_client():
    if not SCHWAB_APP_KEY:
        raise ValueError("SCHWAB_APP_KEY missing from Fly secrets")

    mins = token_minutes_left(TOKEN_PATH)
    if mins < 15:
        print(f"market token low ({mins:.1f} min left); rebuilding Schwab client proactively", flush=True)

    return client_from_token_file(str(TOKEN_PATH), SCHWAB_APP_KEY, SCHWAB_SECRET)

def touch_schwab_token(label, path, mode):
    try:
        if not Path(path).exists():
            print(f"{label} token touch skipped: missing {path}", flush=True)
            return False

        c = client_from_token_file(str(path), SCHWAB_APP_KEY, SCHWAB_SECRET)

        if mode == "quotes":
            r = c.get_quotes(["SPY"])
        elif mode == "accounts":
            r = c.get_account_numbers()
        else:
            raise ValueError(f"unknown token touch mode: {mode}")

        print(f"{label} token touch status: {r.status_code}", flush=True)
        return 200 <= int(r.status_code) < 300

    except Exception as e:
        print(f"{label} token touch error: {type(e).__name__}: {e}", flush=True)
        return False


def touch_both_schwab_tokens():
    touch_schwab_token("MARKET", "/data/schwab_token.json", "quotes")
    touch_schwab_token("TRADING", "/data/schwab_trade_token.json", "accounts")


def extract_last_price(payload):
    """Compatibility scalar price; strategy behavior must remain unchanged."""
    from market_quotes import legacy_scalar_price
    return legacy_scalar_price(payload)


def fetch_quote_batch(client, batch):
    prices = {}

    try:
        resp = client.get_quotes(batch)

        if resp.status_code == 401:
            print("  Schwab quote batch status: 401; rebuilding client and retrying once", flush=True)
            client = get_schwab_client()
            resp = client.get_quotes(batch)

        if resp.status_code != 200:
            print(f"  Schwab quote batch status: {resp.status_code}", flush=True)
            return prices

        data = resp.json()

        for symbol, payload in data.items():
            px = extract_last_price(payload)
            if px is not None:
                prices[symbol.upper()] = px

    except Exception as e:
        print(f"  Schwab quote batch failed: {e}", flush=True)

    return prices


def fetch_schwab_quotes(client, symbols):
    prices = {}

    batches = list(chunk_list(symbols, 500))

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(fetch_quote_batch, client, batch)
            for batch in batches
        ]

        for future in as_completed(futures):
            prices.update(future.result())

    return prices


def fetch_quote_snapshot_batch(client, batch):
    """Fetch normalized rich quotes without discarding execution evidence."""
    from market_quotes import extract_quote_snapshot

    snapshots = {}

    try:
        resp = client.get_quotes(batch)

        if resp.status_code == 401:
            print(
                "  Schwab rich quote batch status: 401; "
                "rebuilding client and retrying once",
                flush=True,
            )
            client = get_schwab_client()
            resp = client.get_quotes(batch)

        if resp.status_code != 200:
            print(
                f"  Schwab rich quote batch status: {resp.status_code}",
                flush=True,
            )
            return snapshots

        data = resp.json()

        for symbol, payload in data.items():
            snapshot = extract_quote_snapshot(symbol, payload)
            if snapshot.legacy_price is not None:
                snapshots[snapshot.symbol] = snapshot

    except Exception as e:
        print(f"  Schwab rich quote batch failed: {e}", flush=True)

    return snapshots


def fetch_schwab_quote_snapshots(client, symbols):
    """Fetch rich snapshots using the same batching/concurrency as legacy."""
    snapshots = {}
    batches = list(chunk_list(symbols, 500))

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(fetch_quote_snapshot_batch, client, batch)
            for batch in batches
        ]

        for future in as_completed(futures):
            snapshots.update(future.result())

    return snapshots


def detect_live_flash_from_quotes(symbol, points, features):
    if len(points) < 8:
        return None

    times = [p[0] for p in points]
    prices = pd.Series([p[1] for p in points], index=pd.to_datetime(times))
    prices = prices[prices > 0].dropna()

    if len(prices) < 8:
        return None

    recent = prices.tail(max(3, int(FLASH_WINDOW_MINUTES * 60 / LIVE_POLL_SECONDS)))
    pre = prices.iloc[:-len(recent)]

    if len(pre) < 5 or len(recent) < 2:
        return None

    flash_start = float(recent.iloc[0])
    flash_end = float(recent.iloc[-1])
    pre_start = float(pre.iloc[0])
    pre_end = float(pre.iloc[-1])

    pre_return_pct = ((pre_end / pre_start) - 1) * 100
    flash_drop_pct = ((flash_start - flash_end) / flash_start) * 100

    if pre_return_pct < MIN_PRE_CRASH_RETURN_PCT:
        return None
    if flash_drop_pct < FLASH_DROP_PCT or flash_drop_pct > MAX_FLASH_DROP_PCT:
        return None

    return {
        "symbol": symbol,
        "detected_at": str(times[-1]),
        "entry_price": flash_end,
        "flash_start_price": flash_start,
        "flash_drop_pct": flash_drop_pct,
        "pre_crash_return_pct": pre_return_pct,
        "target_price": flash_end + 0.60 * (flash_start - flash_end),
        "stop_price": flash_end * 0.95,
        **features,
    }


def main():
    BAD_TICKERS = {"SEMR", "FOLD", "DAWN", "CTRA", "CUK"}
    DAILY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"trendline_scanner_v25_live_schwab.py started at {now_label()}")
    print("SAFE MODE: alerts only. No paper trades. No real trades.")
    print(f"US regular market open now: {is_us_regular_market_open()}")

    symbols = load_symbols()
    symbols = [x for x in symbols if x not in BAD_TICKERS]
    bad_symbols = load_bad_symbols()
    if bad_symbols:
        symbols = [s for s in symbols if s not in bad_symbols]
    print(f"[{now_label()}] Loaded {len(symbols)} symbols after excluding {len(bad_symbols)} bad symbols")

    t0 = time.perf_counter()
    today = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    eligible_cache = Path("/data") / f"eligible_symbols_{today.strftime('%Y%m%d')}.csv"

    eligible = []
    features_by_symbol = {}

    if eligible_cache.exists():
        cached = pd.read_csv(eligible_cache)
        eligible = cached["symbol"].astype(str).tolist()
        for _, row in cached.iterrows():
            sym = str(row["symbol"])
            features_by_symbol[sym] = {
                k: row[k]
                for k in cached.columns
                if k != "symbol"
            }
        refreshed = 0
        missing_bad = 0
        print(f"[{now_label()}] Loaded eligible cache: {len(eligible)} symbols from {eligible_cache}")
    else:
        refreshed, missing_bad = refresh_daily_cache_batch(symbols, today=today, batch_size=BATCH_SIZE)

        for n, symbol in enumerate(symbols, start=1):
            close = load_daily_close(symbol)
            volume = load_daily_volume(symbol)
            features = compute_longterm_features(close)
            liquidity = compute_liquidity_features(volume)
            if (
                features is not None
                and features["pass_longterm"]
                and liquidity["pass_liquidity"]
            ):
                eligible.append(symbol)
                features_by_symbol[symbol] = {**features, **liquidity}
            if n % 500 == 0:
                print(f"  long-term scan progress: {n}/{len(symbols)}")

        rows = []
        for sym in eligible:
            row = {"symbol": sym}
            row.update(features_by_symbol.get(sym, {}))
            rows.append(row)

        pd.DataFrame(rows).to_csv(eligible_cache, index=False)
        print(f"[{now_label()}] Saved eligible cache: {eligible_cache}")

    print(f"[{now_label()}] Daily cache refreshed/updated: {refreshed}")
    print(f"[{now_label()}] Daily cache missing/bad: {missing_bad}")
    print(f"[{now_label()}] Long-term eligible: {len(eligible)} in {time.perf_counter() - t0:.2f}s")

    print(f"[{now_label()}] Connecting to Schwab...")
    client = None  # created fresh each scan cycle so Schwab token can refresh
    print(f"[{now_label()}] Connected to Schwab.")

    history = defaultdict(lambda: deque(maxlen=int((ROLLING_MINUTES_TO_KEEP * 60) / LIVE_POLL_SECONDS)))
    all_alerts = []

    prev_cycle_start = None

    for cycle in range(1, LIVE_MAX_CYCLES + 1):
        cycle_start = time.perf_counter()
        timestamp = datetime.now()

        client = get_schwab_client()
        prices = fetch_schwab_quotes(client, eligible)
        alerts = []

        nearest = None

        for symbol, px in prices.items():
            history[symbol].append((timestamp, px))
            pts = list(history[symbol])
            event = detect_live_flash_from_quotes(symbol, pts, features_by_symbol.get(symbol, {}))

            if len(pts) >= 8:
                recent = pd.Series([p[1] for p in pts]).tail(max(3, int(FLASH_WINDOW_MINUTES * 60 / LIVE_POLL_SECONDS)))
                if len(recent) >= 2:
                    flash_start = float(recent.iloc[0])
                    flash_end = float(recent.iloc[-1])
                    if flash_start > 0:
                        drop_pct = ((flash_start - flash_end) / flash_start) * 100
                        gap_pct = FLASH_DROP_PCT - drop_pct
                        cand = (gap_pct, symbol, drop_pct, flash_end)
                        if nearest is None or cand[0] < nearest[0]:
                            nearest = cand

            if event:
                alerts.append(event)
                all_alerts.append(event)

        print(
            f"[{now_label()}] live cycle {cycle}/{LIVE_MAX_CYCLES} | "
            f"quotes: {len(prices)}/{len(eligible)} | alerts: {len(alerts)} | "
            f"elapsed: {time.perf_counter() - cycle_start:.2f}s"
        )

        if nearest:
            gap_pct, sym, drop_pct, last_px = nearest
            print(
                f"[{now_label()}] nearest | {sym} drop={drop_pct:.2f}% "
                f"need={FLASH_DROP_PCT:.2f}% gap={gap_pct:.2f}% price={last_px:.2f}"
            )

        for a in alerts[:10]:
            print(f"ALERT {a['symbol']} drop={a['flash_drop_pct']:.2f}% entry={a['entry_price']:.2f}")

        if cycle < LIVE_MAX_CYCLES:
            for remaining in range(LIVE_POLL_SECONDS, 0, -1):
                    print(f"\rNext scan in {remaining:2d}s", end="", flush=True)
                    time.sleep(1)
    print()

    if all_alerts:
        out = pd.DataFrame(all_alerts)
        outfile = OUTPUT_DIR / f"schwab_live_alerts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        out.to_csv(outfile, index=False)
        print(f"Saved alerts: {outfile}")

    print("Done. Alerts only. No trades placed.")


if __name__ == "__main__":
    cleanup_quote_tapes()
    ensure_data_token()
    main()
