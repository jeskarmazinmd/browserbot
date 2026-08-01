import os, glob, time, json, math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from schwab_clients import SchwabTradeClient
from bot_output import write_bot_output, append_bot_event
from quote_source import LiveQuoteSource

TAPE_DIR = "/data/tapes"
STATE_FILE = "/data/positions.json"
TRIGGER_OUTCOMES_FILE = "/data/trigger_trade_outcomes.jsonl"

PRE_CRASH_TREND_MINUTES = 30
FLASH_WINDOW_MINUTES = 3
MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR = 0.50
MIN_PRE_CRASH_RETURN_PCT = 0.25
FLASH_DROP_PCT = 1.0
STRATEGY_D_FLASH_DROP_PCT = 0.9
# Strategy H: broad, filtered rebound setup derived from A signals + near misses.
STRATEGY_H_MIN_FLASH_DROP_PCT = 0.60
STRATEGY_H_MAX_FLASH_DROP_PCT = 2.50
STRATEGY_H_MIN_PRE_R2 = 0.40
STRATEGY_H_MAX_PRE_SLOPE_PCT_PER_HOUR = 12.0
STRATEGY_H_STOP_LOSS_FRACTION_BELOW_ENTRY = 0.04
STRATEGY_H_MIN_REMAINING_UPSIDE_PCT = 0.10
NEAR_MISS_SCORE_CUTOFF = 0.25
MAX_FLASH_DROP_PCT = 12.0
MIN_FLASH_DOLLAR_VOLUME_3M = 100_000

RECOVERY_TARGET_FRACTION = 0.60
STOP_LOSS_FRACTION_BELOW_ENTRY = 0.05

ENTRY_CUTOFF_HOUR_ET = 15
ENTRY_CUTOFF_MINUTE_ET = 30


QTY = 1
BUY_LIMIT_BUFFER_PCT = 0.002
REBOUND_CONFIRMATION_PCT = 0.001  # Strategy A: 0.10% rebound
STRATEGY_B_REBOUND_CONFIRMATION_PCT = 0.002  # Strategy B: 0.20% rebound
STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY = 0.02
STRATEGY_D_REBOUND_CONFIRMATION_PCT = STRATEGY_B_REBOUND_CONFIRMATION_PCT
STRATEGY_D_STOP_LOSS_FRACTION_BELOW_ENTRY = STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY
MIN_REMAINING_UPSIDE_PCT = 0.20
PENDING_REBOUND_TIMEOUT_SECONDS = 600  # Allow up to 10 minutes for a flat base/rebound
ENTRY_TIMEOUT_SECONDS = 60

# Forced exit before regular market close.
# 15:55 ET = 12:55 PT.
EOD_EXIT_HOUR_ET = 15
EOD_EXIT_MINUTE_ET = 55
MAX_ORDER_ATTEMPTS_PER_BOOT = 10
POLL_SECONDS = 5
MAX_QUOTE_AGE_SECONDS = 300

attempted = set()

STRATEGY_A = "A"
STRATEGY_B = "B"
STRATEGY_D = "D"
STRATEGY_H = "H"
STRATEGY_CONFIGS = {
    STRATEGY_A: {
        "flash_drop_pct": FLASH_DROP_PCT,
        "rebound_confirmation_pct": REBOUND_CONFIRMATION_PCT,
        "stop_loss_fraction": STOP_LOSS_FRACTION_BELOW_ENTRY,
        "live_order_placement": True,
    },
    STRATEGY_B: {
        "flash_drop_pct": FLASH_DROP_PCT,
        "rebound_confirmation_pct": STRATEGY_B_REBOUND_CONFIRMATION_PCT,
        "stop_loss_fraction": STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY,
        "live_order_placement": False,
    },
    STRATEGY_D: {
        "flash_drop_pct": STRATEGY_D_FLASH_DROP_PCT,
        "rebound_confirmation_pct": STRATEGY_D_REBOUND_CONFIRMATION_PCT,
        "stop_loss_fraction": STRATEGY_D_STOP_LOSS_FRACTION_BELOW_ENTRY,
        "live_order_placement": False,
    },
    STRATEGY_H: {
        "flash_drop_pct": STRATEGY_H_MIN_FLASH_DROP_PCT,
        "max_flash_drop_pct": STRATEGY_H_MAX_FLASH_DROP_PCT,
        "min_pre_r2": STRATEGY_H_MIN_PRE_R2,
        "max_pre_slope_pct_per_hour": STRATEGY_H_MAX_PRE_SLOPE_PCT_PER_HOUR,
        "rebound_confirmation_pct": REBOUND_CONFIRMATION_PCT,
        "stop_loss_fraction": STRATEGY_H_STOP_LOSS_FRACTION_BELOW_ENTRY,
        "min_remaining_upside_pct": STRATEGY_H_MIN_REMAINING_UPSIDE_PCT,
        "live_order_placement": False,
    },
}

# Independent strategy research pack. These are native paper signals and do not
# depend on Strategy A or its flash-drop/rebound event.
INDEPENDENT_FORWARD_START_UTC = "2026-07-31T13:30:00+00:00"
INDEPENDENT_STRATEGY_IDS = ("TF1", "BO1", "OR1", "RS1", "RS2", "RS3", "VE1", "VR1", "M1", "M2", "M3", "MC1", "TL1", "AV1", "TD1", "SH1", "CV1", "HL1", "VT1", "PD1", "EMA1", "EMA2", "EMA3", "SMA1", "VWEMA1")
INDEPENDENT_COOLDOWN_MINUTES = 30
INDEPENDENT_MIN_PRICE = 1.00
INDEPENDENT_MAX_PRICE = 1000.00
UNIVERSE_MANIFEST_DIR = Path("/data")
_UNIVERSE_MANIFEST_CACHE = {"path": None, "mtime_ns": None, "symbols": {}}

# First-pass thresholds intentionally remain simple and frozen prospectively.
TF1_MIN_RETURN_30M_PCT = 0.75
TF1_MIN_R2 = 0.60
TF1_PULLBACK_MIN_PCT = 0.25
TF1_PULLBACK_MAX_PCT = 0.75
TF1_REBOUND_2M_PCT = 0.10

BO1_LOOKBACK_MINUTES = 10
BO1_MAX_RANGE_PCT = 0.75
BO1_BREAK_BUFFER_PCT = 0.10
BO1_MIN_VOLUME_RATIO = 1.50

OR1_RANGE_END_MINUTE_ET = 9 * 60 + 45
OR1_ENTRY_END_MINUTE_ET = 10 * 60 + 15
OR1_BREAK_BUFFER_PCT = 0.10
OR1_MIN_RANGE_PCT = 0.20
OR1_MAX_RANGE_PCT = 2.50

RS1_MIN_RETURN_30M_PCT = 0.75
RS1_MIN_EXCESS_VS_SPY_PCT = 0.75
RS1_MIN_R2 = 0.50

VE1_COMPRESSION_MINUTES = 15
VE1_MAX_COMPRESSION_RANGE_PCT = 0.60
VE1_BREAK_BUFFER_PCT = 0.10
VE1_MIN_VOLUME_RATIO = 1.50

VR1_MIN_DEPTH_BELOW_VWAP_PCT = 0.40
VR1_HOLD_MINUTES = 2

# New native forward-paper research pack. Frozen before the 2026-08-03 session.
NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"
MC1_MIN_RETURN_15M_PCT = 0.80
MC1_MIN_RETURN_5M_PCT = 0.25
MC1_MIN_R2_30M = 0.55
MC1_MAX_DISTANCE_FROM_10M_HIGH_PCT = 0.35
TL1_MIN_R2_30M = 0.45
TL1_MIN_PRIOR_GAP_BELOW_TREND_PCT = 0.25
AV1_MIN_DRAWDOWN_PCT = 0.40
AV1_VOLATILITY_MULTIPLIER = 2.0
AV1_MIN_REBOUND_2M_PCT = 0.10
TD1_START_MINUTE_ET = 10 * 60
TD1_END_MINUTE_ET = 11 * 60 + 30
TD1_MIN_RETURN_30M_PCT = 0.60
TD1_MIN_EXCESS_VS_SPY_PCT = 0.50
SH1_MIN_DECLINE_20M_PCT = 1.00
SH1_MIN_FLATTENING_RATIO = 0.50
CV1_MIN_SLOPE_IMPROVEMENT_PCT_PER_HOUR = 0.80
CV1_MIN_REBOUND_FROM_LOW_PCT = 0.25
HL1_MIN_HIGHER_LOW_PCT = 0.15
HL1_BREAK_BUFFER_PCT = 0.10
VT1_MIN_R2_45M = 0.45
VT1_MAX_CONFLUENCE_DISTANCE_PCT = 0.20
VT1_MIN_REBOUND_2M_PCT = 0.10
PD1_MIN_ONE_MINUTE_DROP_PCT = 1.00
PD1_MIN_REBOUND_FROM_LOW_PCT = 0.40

# Moving-average research family. MA1 (200 EMA reclaim) is intentionally
# deferred because the live cache currently retains only 75 minutes.
EMA_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"
EMA1_FAST_SPAN = 9
EMA1_SLOW_SPAN = 21
EMA1_MIN_VOLUME_RATIO = 1.20
EMA2_SPAN = 20
EMA2_MAX_PULLBACK_DISTANCE_PCT = 0.35
EMA2_MIN_BOUNCE_2M_PCT = 0.10
EMA3_FAST_SPAN = 9
EMA3_MID_SPAN = 21
EMA3_SLOW_SPAN = 50
EMA3_ALIGNMENT_MINUTES = 5
EMA3_BREAKOUT_LOOKBACK_MINUTES = 10
EMA3_BREAK_BUFFER_PCT = 0.05
SMA1_FAST_WINDOW = 20
SMA1_SLOW_WINDOW = 50
SMA1_CONFIRM_MINUTES = 2
VWEMA1_EMA_SPAN = 20
VWEMA1_MIN_RETURN_15M_PCT = 0.30
VWEMA1_MIN_PRICE_ABOVE_VWAP_PCT = 0.05

# M1-M3: slower, independent mean-reversion research. A qualifying decline must
# be distributed across the lookback, make its low before the latest two minutes,
# stabilize, and begin rebounding. All signals are paper-only.
MEDIUM_REVERSAL_CONFIGS = {
    "M1": {"lookback_minutes": 15, "min_decline_pct": 1.50, "min_rebound_from_low_pct": 0.25, "min_rebound_2m_pct": 0.10, "target_pct": 0.75, "stop_pct": 0.75},
    "M2": {"lookback_minutes": 30, "min_decline_pct": 2.25, "min_rebound_from_low_pct": 0.30, "min_rebound_2m_pct": 0.12, "target_pct": 1.00, "stop_pct": 1.00},
    "M3": {"lookback_minutes": 60, "min_decline_pct": 3.25, "min_rebound_from_low_pct": 0.40, "min_rebound_2m_pct": 0.15, "target_pct": 1.25, "stop_pct": 1.25},
}
MEDIUM_REVERSAL_MIN_LOW_AGE_MINUTES = 2
MEDIUM_REVERSAL_MAX_LOW_AGE_MINUTES = 10
MEDIUM_REVERSAL_MAX_SINGLE_MINUTE_SHARE = 0.75

def append_strategy_event(strategy_id, event_type, **payload):
    append_bot_event(event_type, strategy_id=strategy_id, **payload)

def append_ab_paper_event(event_type, **payload):
    """Use only for genuinely identical research events such as near misses."""
    for strategy_id in (STRATEGY_A, STRATEGY_B):
        append_strategy_event(strategy_id, event_type, **payload)


def strategy_accepts_flash(strategy_id, event):
    """Apply strategy-specific admission filters to one detected flash."""
    cfg = STRATEGY_CONFIGS[strategy_id]
    drop = float(event.get("flash_drop_pct", 0) or 0)
    if drop < float(cfg["flash_drop_pct"]):
        return False
    if drop > float(cfg.get("max_flash_drop_pct", MAX_FLASH_DROP_PCT)):
        return False

    min_r2 = cfg.get("min_pre_r2")
    if min_r2 is not None:
        r2 = float(event.get("pre_r2", float("nan")) or float("nan"))
        if math.isnan(r2) or r2 < float(min_r2):
            return False

    max_slope = cfg.get("max_pre_slope_pct_per_hour")
    if max_slope is not None:
        slope = float(event.get("pre_slope_pct_per_hour", float("nan")) or float("nan"))
        if math.isnan(slope) or slope > float(max_slope):
            return False
    return True


def is_regular_market_hours_et():
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() >= 5:
        return False
    start = now.replace(hour=9, minute=30, second=0, microsecond=0)
    end = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return start <= now < end



def token_minutes_left(token_path):
    try:
        data = json.loads(Path(token_path).read_text())
        tok = data.get("token", data)
        exp = tok.get("expires_at")
        if exp is None:
            return -999
        return (float(exp) - time.time()) / 60
    except Exception:
        return -999


def explicit_refresh_schwab_token(token_path, app_key, app_secret):
    import base64
    import requests

    path = Path(token_path)
    data = json.loads(path.read_text())
    tok = data.get("token", data)
    refresh_token = tok.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("missing refresh_token")

    basic = base64.b64encode(f"{app_key}:{app_secret}".encode()).decode()
    r = requests.post(
        "https://api.schwabapi.com/v1/oauth/token",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=20,
    )
    if r.status_code != 200:
        raise RuntimeError(f"refresh failed status={r.status_code} body={r.text[:500]}")

    new_tok = r.json()
    now = time.time()
    new_tok["expires_at"] = now + float(new_tok.get("expires_in", 1800))

    # Preserve refresh token if Schwab does not return a new one.
    if "refresh_token" not in new_tok:
        new_tok["refresh_token"] = refresh_token

    data["token"] = new_tok
    path.write_text(json.dumps(data, indent=2))
    return token_minutes_left(path)

VOLUME_METRIC_KEYS = (
    "volume_data_status_flash",
    "flash_volume_1m",
    "flash_volume_3m",
    "avg_volume_1m_pre30",
    "flash_volume_ratio",
    "flash_dollar_volume_1m",
    "flash_dollar_volume_3m",
    "flash_snapshot_time",
    "flash_price_snapshot",
    "rolling_vwap_45m",
    "distance_below_rolling_vwap_pct",
    "pre30_return_std_pct",
    "flash_drop_volatility_units",
    "volume_data_status_rebound",
    "rebound_volume_1m",
    "rebound_volume_total",
    "rebound_volume_ratio",
    "rebound_dollar_volume_1m",
    "rebound_dollar_volume_total",
    "rebound_snapshot_time",
)


def _market_data_client():
    """Build the existing Schwab market-data client without touching the quote tape."""
    from schwab.auth import client_from_token_file

    app_key = os.environ.get("SCHWAB_MARKET_APP_KEY") or os.environ.get("SCHWAB_APP_KEY")
    app_secret = os.environ.get("SCHWAB_MARKET_SECRET") or os.environ.get("SCHWAB_SECRET")
    if not app_key or not app_secret:
        raise RuntimeError("Schwab market-data app key/secret missing")
    return client_from_token_file(
        "/data/schwab_token.json",
        app_key,
        app_secret,
    )


def _minute_candles(symbol, lookback_minutes=45):
    """Fetch recent Schwab 1-minute candles for one symbol; failures stay non-fatal."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=max(lookback_minutes, 40))
    client = _market_data_client()
    response = client.get_price_history_every_minute(
        symbol,
        start_datetime=start,
        end_datetime=end,
        need_extended_hours_data=False,
        need_previous_close=False,
    )
    if int(getattr(response, "status_code", 0)) != 200:
        raise RuntimeError(f"price history status={getattr(response, 'status_code', 'NA')}")

    payload = response.json() or {}
    candles = payload.get("candles") or []
    rows = []
    for candle in candles:
        try:
            ts = pd.to_datetime(candle.get("datetime"), unit="ms", utc=True)
            volume = float(candle.get("volume") or 0)
            close = float(candle.get("close") or 0)
            if pd.notna(ts) and volume >= 0 and close > 0:
                rows.append({"timestamp": ts, "volume": volume, "close": close})
        except Exception:
            continue
    if not rows:
        raise RuntimeError("no usable one-minute candles returned")
    return pd.DataFrame(rows).sort_values("timestamp").drop_duplicates("timestamp", keep="last")


def fetch_flash_volume_metrics(symbol):
    """Freeze volume conditions when the flash first qualifies."""
    snapshot_time = datetime.now(timezone.utc).isoformat()
    empty = {
        "volume_data_status_flash": "ERROR",
        "flash_snapshot_time": snapshot_time,
    }
    try:
        df = _minute_candles(symbol, lookback_minutes=45)
        # Include Schwab's latest candle, which may be the still-forming minute.
        # That aligns the snapshot with the live flash qualification time.
        if len(df) < 33:
            raise RuntimeError(f"insufficient one-minute candles: {len(df)}")

        flash = df.tail(3)
        baseline = df.iloc[-33:-3]
        avg_pre30 = float(baseline["volume"].mean())
        flash_1m = float(flash.iloc[-1]["volume"])
        flash_3m = float(flash["volume"].sum())
        flash_dollar_1m = float(flash.iloc[-1]["volume"] * flash.iloc[-1]["close"])
        flash_dollar_3m = float((flash["volume"] * flash["close"]).sum())
        ratio = (flash_3m / 3.0) / avg_pre30 if avg_pre30 > 0 else None
        snapshot_price = float(flash.iloc[-1]["close"])
        total_volume = float(df["volume"].sum())
        rolling_vwap = float((df["volume"] * df["close"]).sum() / total_volume) if total_volume > 0 else None
        distance_below_vwap = ((rolling_vwap / snapshot_price) - 1.0) * 100.0 if rolling_vwap and snapshot_price > 0 else None
        pre_returns = baseline["close"].pct_change().dropna() * 100.0
        pre30_std = float(pre_returns.std(ddof=0)) if len(pre_returns) >= 5 else None

        return {
            "volume_data_status_flash": "OK",
            "flash_volume_1m": flash_1m,
            "flash_volume_3m": flash_3m,
            "avg_volume_1m_pre30": avg_pre30,
            "flash_volume_ratio": ratio,
            "flash_dollar_volume_1m": flash_dollar_1m,
            "flash_dollar_volume_3m": flash_dollar_3m,
            "flash_price_snapshot": snapshot_price,
            "rolling_vwap_45m": rolling_vwap,
            "distance_below_rolling_vwap_pct": distance_below_vwap,
            "pre30_return_std_pct": pre30_std,
            "flash_drop_volatility_units": None,
            "flash_snapshot_time": snapshot_time,
        }
    except Exception as exc:
        empty["volume_data_error_flash"] = f"{type(exc).__name__}: {exc}"
        print(f"FLASH_VOLUME_SNAPSHOT_ERROR {symbol}: {empty['volume_data_error_flash']}", flush=True)
        return empty


def fetch_rebound_volume_metrics(symbol, pending_created_at, avg_volume_1m_pre30=None):
    """Freeze volume conditions at rebound confirmation, including the live minute."""
    snapshot_time = datetime.now(timezone.utc).isoformat()
    empty = {
        "volume_data_status_rebound": "ERROR",
        "rebound_snapshot_time": snapshot_time,
    }
    try:
        df = _minute_candles(symbol, lookback_minutes=45)
        created = pd.Timestamp(pending_created_at)
        created = created.tz_localize("UTC") if created.tzinfo is None else created.tz_convert("UTC")
        start_minute = created.floor("min")
        rebound = df[df["timestamp"] >= start_minute]
        if rebound.empty:
            rebound = df.tail(1)

        latest = rebound.iloc[-1]
        rebound_1m = float(latest["volume"])
        rebound_total = float(rebound["volume"].sum())
        dollar_1m = float(latest["volume"] * latest["close"])
        dollar_total = float((rebound["volume"] * rebound["close"]).sum())
        baseline = float(avg_volume_1m_pre30 or 0)
        ratio = rebound_1m / baseline if baseline > 0 else None

        return {
            "volume_data_status_rebound": "OK",
            "rebound_volume_1m": rebound_1m,
            "rebound_volume_total": rebound_total,
            "rebound_volume_ratio": ratio,
            "rebound_dollar_volume_1m": dollar_1m,
            "rebound_dollar_volume_total": dollar_total,
            "rebound_snapshot_time": snapshot_time,
        }
    except Exception as exc:
        empty["volume_data_error_rebound"] = f"{type(exc).__name__}: {exc}"
        print(f"REBOUND_VOLUME_SNAPSHOT_ERROR {symbol}: {empty['volume_data_error_rebound']}", flush=True)
        return empty


def _copy_volume_metrics(source):
    return {key: source.get(key) for key in VOLUME_METRIC_KEYS if source.get(key) is not None}


def proactive_schwab_token_refresh(market_client=None, trade_client=None):
    """
    Force schwab-py to refresh expired/near-expired access tokens by making
    harmless authenticated requests. Does not place orders.
    """
    try:
        if market_client is not None:
            r = market_client.get_quotes(["VOO"])
            print(f"TOKEN_REFRESH_MARKET status={getattr(r, 'status_code', 'NA')}", flush=True)
    except Exception as e:
        print(f"TOKEN_REFRESH_MARKET_ERROR {repr(e)}", flush=True)

    try:
        if trade_client is not None:
            r = trade_client.get_account_numbers()
            print(f"TOKEN_REFRESH_TRADE status={getattr(r, 'status_code', 'NA')}", flush=True)
    except Exception as e:
        print(f"TOKEN_REFRESH_TRADE_ERROR {repr(e)}", flush=True)

def latest_tape():
    files = sorted(glob.glob(f"{TAPE_DIR}/quotes_*.csv"))
    return files[-1] if files else None

def allow_new_entries_now():
    now_et = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
    cutoff = now_et.replace(
        hour=ENTRY_CUTOFF_HOUR_ET,
        minute=ENTRY_CUTOFF_MINUTE_ET,
        second=0,
        microsecond=0,
    )
    return now_et < cutoff

# Incremental tape reader state. The raw tape remains on disk for restart
# recovery, while the live strategy keeps only minute-level observations.
_TAPE_CACHE = None
_TAPE_PATH = None
_TAPE_OFFSET = 0
_TAPE_INODE = None
_TAPE_PARTIAL = b""

CACHE_MINUTES = 75
INITIAL_TAIL_ROWS = 900_000


def _parse_quote_bytes(payload):
    """Parse complete raw CSV rows from an in-memory byte payload."""
    import io

    if not payload:
        return pd.DataFrame(columns=["timestamp", "symbol", "price"])

    df = pd.read_csv(
        io.BytesIO(payload),
        names=["timestamp", "symbol", "price"],
        dtype={"symbol": "string"},
        low_memory=False,
    )

    df = df[df["timestamp"] != "timestamp_utc"]
    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        format="ISO8601",
        errors="coerce",
        utc=True,
    )
    df["price"] = pd.to_numeric(df["price"], errors="coerce")

    return df.dropna(subset=["timestamp", "symbol", "price"])


def _to_minute_cache(df):
    """Collapse raw quotes to the final quote for each symbol/clock minute."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["timestamp", "symbol", "price"])

    work = df.sort_values("timestamp").copy()
    work["timestamp"] = work["timestamp"].dt.floor("min")

    return (
        work.groupby(["symbol", "timestamp"], as_index=False, sort=False)["price"]
        .last()
        [["timestamp", "symbol", "price"]]
        .sort_values(["timestamp", "symbol"])
        .reset_index(drop=True)
    )


def _merge_minute_cache(current, incoming):
    if incoming is None or incoming.empty:
        return current

    if current is None or current.empty:
        merged = incoming.copy()
    else:
        merged = pd.concat([current, incoming], ignore_index=True)

    merged = (
        merged.sort_values(["timestamp", "symbol"])
        .drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    )

    newest = merged["timestamp"].max()
    if pd.notna(newest):
        cutoff = newest - pd.Timedelta(minutes=CACHE_MINUTES)
        merged = merged[merged["timestamp"] >= cutoff]

    return merged.reset_index(drop=True)


def _initialise_tape_cache(tape):
    """Load restart history once, then remember the current byte position."""
    global _TAPE_CACHE, _TAPE_PATH, _TAPE_OFFSET, _TAPE_INODE, _TAPE_PARTIAL

    import subprocess
    import tempfile

    stat_before = tape.stat()
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            subprocess.run(
                ["tail", "-n", str(INITIAL_TAIL_ROWS), str(tape)],
                stdout=tmp,
                stderr=subprocess.DEVNULL,
                check=True,
            )

        payload = tmp_path.read_bytes()
        raw = _parse_quote_bytes(payload)
        _TAPE_CACHE = _to_minute_cache(raw)

        _TAPE_PATH = tape
        _TAPE_OFFSET = stat_before.st_size
        _TAPE_INODE = stat_before.st_ino
        _TAPE_PARTIAL = b""

        print(
            "TAPE_CACHE_INITIALIZED "
            f"raw_rows={len(raw)} minute_rows={len(_TAPE_CACHE)} "
            f"offset={_TAPE_OFFSET}",
            flush=True,
        )
        return _TAPE_CACHE

    except Exception as e:
        print(
            f"tape cache initialization error: {type(e).__name__}: {e}",
            flush=True,
        )
        return None

    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def read_data():
    """Return a rolling minute-level cache, reading only newly appended rows."""
    global _TAPE_CACHE, _TAPE_PATH, _TAPE_OFFSET, _TAPE_INODE, _TAPE_PARTIAL

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    candidates = [
        Path("/data/tapes") / f"quotes_{today}.csv",
        Path(f"quotes_{today}.csv"),
    ]

    tape = next(
        (x for x in candidates if x.exists() and x.stat().st_size > 0),
        None,
    )
    if tape is None:
        return None

    try:
        stat_now = tape.stat()

        # First run, a new trading day, or collector trim via os.replace.
        if (
            _TAPE_CACHE is None
            or _TAPE_PATH != tape
            or _TAPE_INODE != stat_now.st_ino
            or stat_now.st_size < _TAPE_OFFSET
        ):
            return _initialise_tape_cache(tape)

        if stat_now.st_size == _TAPE_OFFSET:
            return _TAPE_CACHE

        with tape.open("rb") as source:
            source.seek(_TAPE_OFFSET)
            chunk = source.read()
            new_offset = source.tell()

        payload = _TAPE_PARTIAL + chunk

        # Parse only complete CSV lines. Preserve a partial final write.
        if payload.endswith(b"\n"):
            complete = payload
            _TAPE_PARTIAL = b""
        else:
            complete, separator, remainder = payload.rpartition(b"\n")
            if not separator:
                _TAPE_PARTIAL = payload
                _TAPE_OFFSET = new_offset
                return _TAPE_CACHE
            complete += b"\n"
            _TAPE_PARTIAL = remainder

        _TAPE_OFFSET = new_offset

        raw_new = _parse_quote_bytes(complete)
        minute_new = _to_minute_cache(raw_new)
        _TAPE_CACHE = _merge_minute_cache(_TAPE_CACHE, minute_new)

        return _TAPE_CACHE

    except Exception as e:
        print(f"incremental tape read error: {type(e).__name__}: {e}", flush=True)
        return _TAPE_CACHE



quote_source = LiveQuoteSource(read_data)


def set_quote_source(source):
    global quote_source
    quote_source = source

def fit_log_slope_pct_per_hour(prices):
    prices = prices.dropna()
    prices = prices[prices > 0]
    if len(prices) < 5:
        return math.nan, math.nan

    y = np.log(prices.to_numpy(dtype=float))
    x = np.arange(len(y), dtype=float) / 60.0

    try:
        slope, intercept = np.polyfit(x, y, 1)
    except Exception:
        return math.nan, math.nan

    y_hat = slope * x + intercept
    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else math.nan

    return (math.exp(slope) - 1) * 100, r2

def load_positions():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_positions(positions):
    with open(STATE_FILE, "w") as f:
        json.dump(positions, f, indent=2)

def _parse_utc(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def append_trigger_outcome(record):
    """Append one durable, completed real-trade outcome, idempotently."""
    path = Path(TRIGGER_OUTCOMES_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    trade_id = record.get("trade_id")
    if trade_id and path.exists():
        try:
            with path.open() as existing:
                for raw in existing:
                    try:
                        if json.loads(raw).get("trade_id") == trade_id:
                            return
                    except Exception:
                        pass
        except Exception:
            pass
    with path.open("a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _finalize_real_trade(trader, sym, pos, now_utc):
    """Resolve the actual broker exit and persist realized P/L plus MFE/MAE."""
    exit_result = trader.find_latest_filled_sell(
        sym, entered_after=pos.get("entry_fill_time") or pos.get("submitted_at")
    )
    match = exit_result.get("match") if exit_result.get("ok") else None
    if not match or not match.get("average_price"):
        return False

    entry_price = float(pos.get("actual_entry_price") or pos.get("entry_price") or 0)
    exit_price = float(match["average_price"])
    if entry_price <= 0:
        return False

    entry_time = _parse_utc(pos.get("entry_fill_time") or pos.get("submitted_at"))
    exit_time = _parse_utc(match.get("fill_time")) or now_utc
    holding_minutes = (exit_time - entry_time).total_seconds() / 60.0 if entry_time else None
    highest = max(float(pos.get("highest_price_since_fill") or entry_price), exit_price)
    lowest = min(float(pos.get("lowest_price_since_fill") or entry_price), exit_price)
    qty = float(pos.get("filled_qty") or pos.get("qty") or 0)
    ret_pct = (exit_price / entry_price - 1) * 100
    pnl = (exit_price - entry_price) * qty

    order_type = str(match.get("order_type") or "").upper()
    if pos.get("eod_order_id") and str(match.get("order_id")) == str(pos.get("eod_order_id")):
        reason = "EOD"
    elif order_type == "STOP":
        reason = "STOP"
    elif order_type == "LIMIT":
        reason = "TARGET"
    else:
        reason = "SELL_FILLED"

    try:
        mfe_time = _parse_utc(pos.get("mfe_at"))
        time_to_mfe_minutes = (
            max(0.0, (mfe_time - entry_time).total_seconds() / 60.0)
            if mfe_time and entry_time else None
        )
    except Exception:
        time_to_mfe_minutes = None
    mae_pct = (lowest / entry_price - 1) * 100
    stop_replay = {
        f"stop_{str(level).replace('.', '_')}pct_hit": mae_pct <= -level
        for level in (1.0, 1.5, 2.0, 2.5, 3.0, 5.0)
    }

    record = {
        "trade_id": f"{pos.get('entry_order_id')}|{sym}",
        "symbol": sym,
        "signal_time": pos.get("signal_time"),
        "order_submitted_time": pos.get("submitted_at"),
        "entry_order_id": pos.get("entry_order_id"),
        "entry_fill_time": pos.get("entry_fill_time"),
        "entry_fill_price": entry_price,
        "filled_qty": qty,
        "exit_order_id": match.get("order_id"),
        "exit_fill_time": exit_time.isoformat(),
        "exit_fill_price": exit_price,
        "exit_reason": reason,
        "holding_minutes": holding_minutes,
        "highest_price": highest,
        "mfe_pct": (highest / entry_price - 1) * 100,
        "mfe_at": pos.get("mfe_at"),
        "time_to_mfe_minutes": time_to_mfe_minutes,
        "time_to_target_minutes": holding_minutes if reason == "TARGET" else None,
        "lowest_price": lowest,
        "mae_pct": mae_pct,
        "stop_replay": stop_replay,
        "recovery_fraction_at_entry": pos.get("recovery_fraction_at_entry"),
        "pending_created_at": pos.get("pending_created_at"),
        "confirmation_wait_seconds": pos.get("confirmation_wait_seconds"),
        "running_low_price": pos.get("running_low_price"),
        "actual_rebound_pct": pos.get("actual_rebound_pct"),
        "remaining_upside_pct": pos.get("remaining_upside_pct"),
        "mae_at": pos.get("mae_at"),
        "return_pct": ret_pct,
        "realized_pnl": pnl,
        "flash_drop_pct": pos.get("flash_drop_pct"),
        "pre_return_pct": pos.get("pre_return_pct"),
        "pre_slope_pct_per_hour": pos.get("pre_slope_pct_per_hour"),
        "target_price": pos.get("target_price"),
        "stop_price": pos.get("stop_price"),
        **_copy_volume_metrics(pos),
        "recorded_at": now_utc.isoformat(),
    }
    append_trigger_outcome(record)
    append_bot_event("TRIGGER_TRADE_CLOSED", symbol=sym, outcome=record, position=pos)
    print(f"TRIGGER_TRADE_CLOSED {sym} return={ret_pct:+.2f}% pnl={pnl:+.2f}", flush=True)
    return True


def make_trader():
    token_path = Path("/data/schwab_trade_token.json")

    from schwab.auth import client_from_token_file

    app_key = os.environ.get("SCHWAB_TRADING_APP_KEY")
    app_secret = os.environ.get("SCHWAB_TRADING_SECRET")
    if not app_key or not app_secret:
        raise RuntimeError("SCHWAB_TRADING_APP_KEY/SCHWAB_TRADING_SECRET missing")

    token_data = json.loads(token_path.read_text())
    token_obj = token_data.get("token", {})
    token = token_obj.get("access_token") if isinstance(token_obj, dict) else token_data.get("access_token")

    # schwab-py refreshes token file if needed before/while calling API.
    # If trading auth is bad, disable trading instead of crashing/restarting Fly.
    try:
        client = client_from_token_file(str(token_path), app_key, app_secret)
        r = client.get_account_numbers()
    except Exception as e:
        print(f"TRADING_DISABLED Schwab account lookup failed: {type(e).__name__}: {e}", flush=True)
        t = SchwabTradeClient(token or "", "TRADING_DISABLED")
        t.enabled = False
        return t

    try:
        body = r.json()
    except Exception:
        body = r.text

    if r.status_code != 200:
        print(f"TRADING_DISABLED could not resolve Schwab account hash: status={r.status_code} body={body}", flush=True)
        t = SchwabTradeClient(token or "", "TRADING_DISABLED")
        t.enabled = False
        return t

    if not isinstance(body, list) or not body or not body[0].get("hashValue"):
        print(f"TRADING_DISABLED could not resolve Schwab account hash: unexpected body={body}", flush=True)
        t = SchwabTradeClient(token or "", "TRADING_DISABLED")
        t.enabled = False
        return t

    account_id = body[0]["hashValue"]

    token_data = json.loads(token_path.read_text())
    token_data["account_hash"] = account_id
    token_path.write_text(json.dumps(token_data, indent=2))

    print(f"TOKEN_PRESENT={bool(token)} ACCOUNT_PRESENT={bool(account_id)} TOKEN_PATH={token_path}", flush=True)
    return SchwabTradeClient(
        token,
        account_id,
        sdk_client=client,
    )

def latest_prices(df):
    return df.groupby("symbol")["price"].last().to_dict()

def minute_prices(g):
    """Return one price per minute for the current NY regular session only.

    The signal window must never use premarket, after-hours, or a previous
    trading day's data. Missing RTH minutes remain NaN after resampling so
    detect_latest_flash() rejects discontinuous windows.
    """
    data = g[["timestamp", "price"]].copy()

    data["timestamp"] = pd.to_datetime(
        data["timestamp"],
        utc=True,
        errors="coerce",
    )
    data["price"] = pd.to_numeric(
        data["price"],
        errors="coerce",
    )

    data = (
        data
        .dropna(subset=["timestamp", "price"])
        .sort_values("timestamp")
    )

    if data.empty:
        return pd.Series(dtype=float)

    # Convert each raw quote to New York time and keep only today's
    # regular session: 09:30:00 <= ET < 16:00:00.
    ny = ZoneInfo("America/New_York")
    now_et = datetime.now(timezone.utc).astimezone(ny)
    et = data["timestamp"].dt.tz_convert(ny)

    same_session_date = et.dt.date == now_et.date()
    minutes_since_midnight = et.dt.hour * 60 + et.dt.minute
    in_rth = (
        (minutes_since_midnight >= 9 * 60 + 30)
        & (minutes_since_midnight < 16 * 60)
    )

    data = data[same_session_date & in_rth]

    if data.empty:
        return pd.Series(dtype=float)

    # Use the final quote observed in each clock minute.
    # Do not fill missing minutes: a gap must not be mistaken for
    # continuously observed market data.
    return (
        data
        .set_index("timestamp")["price"]
        .resample("1min")
        .last()
    )

def detect_latest_flash(sym, g, min_flash_drop_pct=FLASH_DROP_PCT):
    prices = minute_prices(g)

    # 31 points span the 30-minute pre-window and 4 points span the
    # 3-minute flash window. The boundary point is shared: 31 + 4 - 1 = 34.
    needed = PRE_CRASH_TREND_MINUTES + FLASH_WINDOW_MINUTES + 1
    if len(prices) < needed:
        return None

    window = prices.iloc[-needed:]

    # The newest bar must belong to the current RTH session and be recent.
    # This prevents the final window from being re-scored after the close or
    # from using stale data if collection has stopped.
    latest_minute = window.index[-1]
    now_utc = pd.Timestamp.now(tz="UTC")
    if latest_minute.tzinfo is None:
        latest_minute = latest_minute.tz_localize("UTC")
    else:
        latest_minute = latest_minute.tz_convert("UTC")
    if (now_utc - latest_minute).total_seconds() > MAX_QUOTE_AGE_SECONDS:
        return None

    # Do not collapse gaps into an apparently shorter interval.
    if window.isna().any():
        return None

    pre = window.iloc[:PRE_CRASH_TREND_MINUTES + 1]
    flash = window.iloc[-(FLASH_WINDOW_MINUTES + 1):]

    if len(pre) < 5 or len(flash) < 2:
        return None

    pre_start = float(pre.iloc[0])
    pre_end = float(pre.iloc[-1])
    flash_start = float(flash.iloc[0])
    flash_end = float(flash.iloc[-1])

    if pre_start <= 0 or flash_start <= 0 or flash_end <= 0:
        return None

    pre_return_pct = ((pre_end / pre_start) - 1) * 100
    pre_slope_pct_per_hour, pre_r2 = fit_log_slope_pct_per_hour(pre)
    flash_drop_pct = ((flash_start - flash_end) / flash_start) * 100

    pass_pre_return = pre_return_pct >= MIN_PRE_CRASH_RETURN_PCT
    pass_pre_slope = not math.isnan(pre_slope_pct_per_hour) and pre_slope_pct_per_hour >= MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR
    pass_flash = min_flash_drop_pct <= flash_drop_pct <= MAX_FLASH_DROP_PCT

    if not (pass_pre_return and pass_pre_slope and pass_flash):
        return None

    entry = flash_end
    target = entry + RECOVERY_TARGET_FRACTION * (flash_start - entry)
    stop = entry * (1 - STOP_LOSS_FRACTION_BELOW_ENTRY)

    return {
        "symbol": sym,
        "entry_price": entry,
        "flash_start_price": flash_start,
        "flash_drop_pct": flash_drop_pct,
        "pre_return_pct": pre_return_pct,
        "pre_slope_pct_per_hour": pre_slope_pct_per_hour,
        "pre_r2": pre_r2,
        "target_price": target,
        "stop_price": stop,
        "signal_window_end": window.index[-1].isoformat(),
    }

def refresh_event_for_entry(event, current_price, strategy_id):
    """Build a confirmed-entry snapshot while preserving the original target."""
    refreshed = dict(event)
    cfg = STRATEGY_CONFIGS[strategy_id]
    entry = float(current_price)
    flash_start = float(refreshed["flash_start_price"])
    original_target = float(refreshed["target_price"])
    original_drop_pct = float(refreshed["flash_drop_pct"])

    remaining_upside_pct = ((original_target / entry) - 1.0) * 100.0
    refreshed.update({
        "strategy_id": strategy_id,
        "entry_price": entry,
        "original_flash_drop_pct": original_drop_pct,
        "original_target_price": original_target,
        "remaining_upside_pct": remaining_upside_pct,
        "target_price": original_target,
        "stop_price": entry * (1 - cfg["stop_loss_fraction"]),
        "rebound_confirmation_pct": cfg["rebound_confirmation_pct"] * 100,
    })
    return refreshed

def validate_confirmed_entry(event):
    entry = float(event.get("entry_price", 0) or 0)
    target = float(event.get("target_price", 0) or 0)
    original_drop = float(event.get("original_flash_drop_pct", event.get("flash_drop_pct", 0)) or 0)
    remaining = float(event.get("remaining_upside_pct", -999) or -999)
    strategy_id = str(event.get("strategy_id") or STRATEGY_A)
    min_remaining = float(
        STRATEGY_CONFIGS.get(strategy_id, {}).get(
            "min_remaining_upside_pct", MIN_REMAINING_UPSIDE_PCT
        )
    )
    if original_drop <= 0:
        return False, "invalid_original_drop"
    if target <= entry:
        return False, "target_reached_before_entry"
    if remaining < min_remaining:
        return False, "insufficient_remaining_upside"
    return True, None


def is_eod_exit_time():
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
    return (now.hour, now.minute) >= (EOD_EXIT_HOUR_ET, EOD_EXIT_MINUTE_ET)


def manage_exits(trader, positions, prices_now):
    """Reconcile orders and positions using Schwab as the source of truth.

    The broker-hosted OCO handles target and stop exits. The runner only
    performs the separate end-of-day close after cancelling the bracket.
    """
    changed = False
    now_utc = datetime.now(timezone.utc)

    active_statuses = {
        "AWAITING_PARENT_ORDER",
        "AWAITING_CONDITION",
        "AWAITING_STOP_CONDITION",
        "AWAITING_MANUAL_REVIEW",
        "ACCEPTED",
        "AWAITING_UR_OUT",
        "PENDING_ACTIVATION",
        "QUEUED",
        "WORKING",
        "PENDING_CANCEL",
        "PARTIALLY_FILLED",
    }

    terminal_failure_statuses = {
        "REJECTED",
        "CANCELED",
        "CANCELLED",
        "EXPIRED",
    }

    for sym, pos in list(positions.items()):
        position_result = trader.get_net_position_qty(sym)

        if not position_result.get("ok"):
            print(
                f"POSITION_QUERY_ERROR {sym}: {position_result}",
                flush=True,
            )
            append_bot_event(
                "POSITION_QUERY_ERROR",
                symbol=sym,
                response=position_result,
                position=pos,
            )
            continue

        actual_qty = float(position_result.get("quantity", 0) or 0)
        pos["actual_qty"] = actual_qty
        pos["last_reconciled_at"] = now_utc.isoformat()
        changed = True

        # No filled position currently exists. A previously confirmed fill
        # becoming flat means the broker-hosted target/stop or EOD sell closed it.
        if actual_qty <= 0 and pos.get("state") in ("ENTRY_FILLED", "POSITION_OPEN", "FILLED"):
            if _finalize_real_trade(trader, sym, pos, now_utc):
                del positions[sym]
                continue

        # No filled position currently exists.
        if actual_qty <= 0:
            eod_order_id = pos.get("eod_order_id")

            if eod_order_id:
                eod_result = trader.get_order(eod_order_id)

                if eod_result.get("ok"):
                    status = str(
                        (eod_result.get("body") or {}).get("status", "")
                    ).upper()

                    pos["eod_order_status"] = status

                    if status in active_statuses:
                        continue

                    if status == "FILLED":
                        print(f"EOD_FLAT_CONFIRMED {sym}", flush=True)
                        append_bot_event(
                            "EOD_FLAT_CONFIRMED",
                            symbol=sym,
                            order_id=eod_order_id,
                            position=pos,
                        )
                        del positions[sym]
                        continue

                    if status in terminal_failure_statuses:
                        pos.pop("eod_order_id", None)
                        pos.pop("eod_order_status", None)

            entry_order_id = pos.get("entry_order_id")

            if entry_order_id:
                entry_result = trader.get_order(entry_order_id)

                if entry_result.get("ok"):
                    status = str(
                        (entry_result.get("body") or {}).get("status", "")
                    ).upper()

                    pos["entry_order_status"] = status

                    if status in active_statuses:
                        # Cancel a stale entry, but do not assume the cancel won
                        # the race against a fill. Reconciliation continues until
                        # Schwab confirms a position or a terminal order state.
                        submitted = _parse_utc(pos.get("submitted_at"))
                        age_seconds = (now_utc - submitted).total_seconds() if submitted else 0
                        last_cancel = _parse_utc(pos.get("last_entry_cancel_attempt_at"))
                        cancel_retry_due = (
                            last_cancel is None
                            or (now_utc - last_cancel).total_seconds() >= 15
                        )
                        if age_seconds >= ENTRY_TIMEOUT_SECONDS and cancel_retry_due:
                            cancel_result = trader.cancel_order(entry_order_id)
                            pos["last_entry_cancel_attempt_at"] = now_utc.isoformat()
                            pos.setdefault("entry_cancel_requested_at", now_utc.isoformat())
                            pos["entry_cancel_response"] = cancel_result
                            pos["state"] = "ENTRY_CANCEL_REQUESTED"
                            append_bot_event(
                                "ENTRY_CANCEL_REQUESTED",
                                symbol=sym,
                                order_id=entry_order_id,
                                age_seconds=age_seconds,
                                response=cancel_result,
                                position=pos,
                            )
                            print(
                                f"ENTRY_CANCEL_REQUESTED {sym} age={age_seconds:.1f}s response={cancel_result}",
                                flush=True,
                            )
                        continue

                    if status == "FILLED":
                        # Capture the parent BUY fill even if the position endpoint
                        # lagged or the child exit completed before this poll.
                        fill = trader.get_order_fill_summary(entry_order_id)
                        if fill.get("ok") and fill.get("average_price"):
                            pos["actual_entry_price"] = float(fill["average_price"])
                            pos["entry_fill_time"] = fill.get("fill_time") or now_utc.isoformat()
                            pos["filled_qty"] = float(fill.get("filled_quantity") or pos.get("qty") or 0)
                            pos.setdefault("highest_price_since_fill", pos["actual_entry_price"])
                            pos.setdefault("lowest_price_since_fill", pos["actual_entry_price"])
                            pos.setdefault("mfe_at", pos["entry_fill_time"])
                            pos.setdefault("mae_at", pos["entry_fill_time"])
                            pos["state"] = "POSITION_OPEN"
                            if _finalize_real_trade(trader, sym, pos, now_utc):
                                del positions[sym]
                                continue
                        pos["state"] = "ENTRY_FILLED_AWAITING_POSITION"
                        continue

                    if status in terminal_failure_statuses:
                        print(
                            f"ENTRY_TERMINAL_WITHOUT_POSITION "
                            f"{sym} status={status}",
                            flush=True,
                        )
                        append_bot_event(
                            "ENTRY_TERMINAL_WITHOUT_POSITION",
                            symbol=sym,
                            status=status,
                            position=pos,
                        )
                        del positions[sym]
                        continue

            # No real position and no demonstrably active entry order.
            # Retain the record if Schwab order status could not be confirmed.
            continue

        # Schwab confirms that a real position exists. Capture actual fill
        # details once, then update MFE/MAE from live prices every cycle.
        if not pos.get("actual_entry_price") and pos.get("entry_order_id"):
            fill = trader.get_order_fill_summary(pos["entry_order_id"])
            if fill.get("ok") and fill.get("average_price"):
                pos["actual_entry_price"] = float(fill["average_price"])
                pos["entry_fill_time"] = fill.get("fill_time") or now_utc.isoformat()
                pos["filled_qty"] = float(fill.get("filled_quantity") or actual_qty)
                pos["highest_price_since_fill"] = pos["actual_entry_price"]
                pos["lowest_price_since_fill"] = pos["actual_entry_price"]
                pos["mfe_at"] = pos["entry_fill_time"]
                pos["mae_at"] = pos["entry_fill_time"]
                append_bot_event("ENTRY_FILL_CONFIRMED", symbol=sym, fill=fill, position=pos)

        pos["state"] = "POSITION_OPEN"
        current_px = prices_now.get(sym)
        if current_px is not None and pos.get("actual_entry_price"):
            current_px = float(current_px)
            if current_px > float(pos.get("highest_price_since_fill", current_px)):
                pos["highest_price_since_fill"] = current_px
                pos["mfe_at"] = now_utc.isoformat()
            if current_px < float(pos.get("lowest_price_since_fill", current_px)):
                pos["lowest_price_since_fill"] = current_px
                pos["mae_at"] = now_utc.isoformat()

        # Target and stop are already working broker-side in the OCO.
        if not is_eod_exit_time():
            continue

        # A previously submitted EOD market sell may still be working.
        eod_order_id = pos.get("eod_order_id")

        if eod_order_id:
            eod_result = trader.get_order(eod_order_id)

            if eod_result.get("ok"):
                status = str(
                    (eod_result.get("body") or {}).get("status", "")
                ).upper()

                pos["eod_order_status"] = status

                if status in active_statuses:
                    continue

                if status == "FILLED":
                    # Position query may lag briefly; wait for the next cycle.
                    continue

                if status in terminal_failure_statuses:
                    pos.pop("eod_order_id", None)
                    pos.pop("eod_order_status", None)
                    changed = True

        last_attempt = pos.get("last_eod_attempt_at")

        if last_attempt:
            try:
                previous = datetime.fromisoformat(last_attempt)

                if previous.tzinfo is None:
                    previous = previous.replace(tzinfo=timezone.utc)

                if (now_utc - previous).total_seconds() < 30:
                    continue
            except Exception:
                pass

        pos["last_eod_attempt_at"] = now_utc.isoformat()
        save_positions(positions)

        print(
            f"EOD_RECONCILE_START {sym} actual_qty={actual_qty}",
            flush=True,
        )
        append_bot_event(
            "EOD_RECONCILE_START",
            symbol=sym,
            actual_qty=actual_qty,
            position=pos,
        )

        cancellation = trader.cancel_active_exit_orders(sym)

        print(
            f"EOD_CANCEL_RESULT {sym}: {cancellation}",
            flush=True,
        )
        append_bot_event(
            "EOD_CANCEL_RESULT",
            symbol=sym,
            response=cancellation,
            position=pos,
        )

        if not cancellation.get("ok"):
            print(
                f"EOD_ABORT_ACTIVE_ORDERS_REMAIN {sym}",
                flush=True,
            )
            append_bot_event(
                "EOD_ABORT_ACTIVE_ORDERS_REMAIN",
                symbol=sym,
                response=cancellation,
                position=pos,
            )
            continue

        # Recheck the actual position after cancelling the bracket.
        recheck = trader.get_net_position_qty(sym)

        if not recheck.get("ok"):
            print(
                f"EOD_POSITION_RECHECK_ERROR {sym}: {recheck}",
                flush=True,
            )
            append_bot_event(
                "EOD_POSITION_RECHECK_ERROR",
                symbol=sym,
                response=recheck,
                position=pos,
            )
            continue

        remaining_qty = float(recheck.get("quantity", 0) or 0)

        if remaining_qty <= 0:
            print(f"EOD_ALREADY_FLAT {sym}", flush=True)
            append_bot_event(
                "EOD_ALREADY_FLAT",
                symbol=sym,
                position=pos,
            )
            del positions[sym]
            continue

        sell_qty = int(remaining_qty)

        if sell_qty <= 0:
            print(
                f"EOD_INVALID_QUANTITY {sym} qty={remaining_qty}",
                flush=True,
            )
            append_bot_event(
                "EOD_INVALID_QUANTITY",
                symbol=sym,
                qty=remaining_qty,
                position=pos,
            )
            continue

        print(
            f"EOD_SELL_ATTEMPT {sym} qty={sell_qty}",
            flush=True,
        )
        append_bot_event(
            "SELL_ATTEMPT",
            symbol=sym,
            qty=sell_qty,
            reason="EOD",
            position=pos,
        )

        response = trader.place_eod_sell_order(sym, qty=sell_qty)

        print(
            f"EOD_SELL_RESPONSE {sym}: {response}",
            flush=True,
        )
        append_bot_event(
            "SELL_RESPONSE",
            symbol=sym,
            qty=sell_qty,
            reason="EOD",
            response=response,
            position=pos,
        )

        if response.get("ok"):
            pos["eod_order_id"] = response.get("order_id")
            pos["eod_order_response"] = response
        else:
            append_bot_event(
                "EOD_SELL_REJECTED",
                symbol=sym,
                qty=sell_qty,
                response=response,
                position=pos,
            )

    if changed:
        save_positions(positions)

def _series_at_least(g, count):
    """Return sorted, finite minute prices for one symbol."""
    work = g.sort_values("timestamp")[["timestamp", "price"]].dropna().copy()
    work = work[work["price"] > 0]
    return work if len(work) >= count else None


def _simple_return_pct(start, end):
    return (float(end) / float(start) - 1.0) * 100.0 if float(start) > 0 else math.nan


def _universe_metadata(symbol, timestamp):
    """Read the collector's daily manifest with a cheap mtime cache."""
    try:
        day = pd.Timestamp(timestamp).tz_convert("UTC").strftime("%Y%m%d")
        path = UNIVERSE_MANIFEST_DIR / f"universe_manifest_{day}.json"
        if not path.exists():
            return {"primary_universe": "UNKNOWN", "universe_memberships": [], "sampling_tier": "UNKNOWN", "dynamic_promoted": False}
        mtime_ns = path.stat().st_mtime_ns
        if _UNIVERSE_MANIFEST_CACHE.get("path") != str(path) or _UNIVERSE_MANIFEST_CACHE.get("mtime_ns") != mtime_ns:
            payload = json.loads(path.read_text())
            _UNIVERSE_MANIFEST_CACHE.update({"path": str(path), "mtime_ns": mtime_ns, "symbols": payload.get("symbols", {})})
        meta = dict(_UNIVERSE_MANIFEST_CACHE.get("symbols", {}).get(str(symbol).upper(), {}) or {})
        return {
            "primary_universe": meta.get("primary_universe", "UNKNOWN"),
            "universe_memberships": meta.get("universe_memberships", []),
            "sampling_tier": meta.get("sampling_tier", "UNKNOWN"),
            "dynamic_promoted": bool(meta.get("dynamic_promoted", False)),
        }
    except Exception:
        return {"primary_universe": "UNKNOWN", "universe_memberships": [], "sampling_tier": "UNKNOWN", "dynamic_promoted": False}


def _independent_signal(strategy_id, sym, timestamp, entry, target_pct, stop_pct, setup, **metrics):
    entry = float(entry)
    return {
        "strategy_id": strategy_id,
        "symbol": str(sym),
        "timestamp": pd.Timestamp(timestamp).isoformat(),
        "entry_price": entry,
        "target_price": entry * (1.0 + float(target_pct) / 100.0),
        "stop_price": entry * (1.0 - float(stop_pct) / 100.0),
        "setup": setup,
        "setup_id": f"{strategy_id}|{sym}|{pd.Timestamp(timestamp).floor('min').isoformat()}",
        "live_order_placement": False,
        **_universe_metadata(sym, timestamp),
        **metrics,
    }



def _ema(series, span):
    return series.ewm(span=int(span), adjust=False).mean()


def _confirm_recent_volume_ratio(symbol, lookback_minutes=30):
    """Fetch volume only after a price-based candidate exists.

    Returns latest completed-minute volume divided by the mean of the preceding
    completed minutes. Failures return None and the volume-gated signal is skipped.
    """
    try:
        candles = _minute_candles(symbol, lookback_minutes=max(lookback_minutes, 40))
        if len(candles) < 12:
            return None
        completed = candles.iloc[:-1] if len(candles) > 1 else candles
        latest_volume = float(completed.iloc[-1]["volume"])
        baseline = completed.iloc[-11:-1]["volume"].astype(float)
        average_volume = float(baseline.mean())
        if average_volume <= 0:
            return None
        return latest_volume / average_volume
    except Exception:
        return None


def detect_independent_signals(sym, g, spy_30m_return_pct=None):
    """Generate native paper signals for six unrelated intraday strategy families.

    All calculations use only data at or before the emitted timestamp. The event
    timestamp is the latest completed minute, making repeated scans idempotent.
    """
    work = _series_at_least(g, 18)
    if work is None:
        return []
    latest = work.iloc[-1]
    ts = latest["timestamp"]
    px = float(latest["price"])
    if not (INDEPENDENT_MIN_PRICE <= px <= INDEPENDENT_MAX_PRICE):
        return []

    et = pd.Timestamp(ts).tz_convert(ZoneInfo("America/New_York"))
    minute_et = et.hour * 60 + et.minute
    prices = work["price"].astype(float)
    signals = []

    # Shared trend measures.
    last30 = prices.tail(31)
    ret30 = _simple_return_pct(last30.iloc[0], last30.iloc[-1]) if len(last30) >= 21 else math.nan
    slope30, r2_30 = fit_log_slope_pct_per_hour(last30) if len(last30) >= 21 else (math.nan, math.nan)

    # TF1: strong orderly trend, shallow pullback from recent high, then renewed rise.
    if len(prices) >= 31 and not math.isnan(ret30) and not math.isnan(r2_30):
        recent_high = float(prices.tail(10).max())
        pullback_pct = (recent_high / px - 1.0) * 100.0 if px > 0 else math.nan
        rebound2 = _simple_return_pct(prices.iloc[-3], prices.iloc[-1])
        if (
            ret30 >= TF1_MIN_RETURN_30M_PCT
            and slope30 > 0
            and r2_30 >= TF1_MIN_R2
            and TF1_PULLBACK_MIN_PCT <= pullback_pct <= TF1_PULLBACK_MAX_PCT
            and rebound2 >= TF1_REBOUND_2M_PCT
        ):
            signals.append(_independent_signal(
                "TF1", sym, ts, px, 0.75, 0.60, "trend_pullback",
                return_30m_pct=ret30, slope_30m_pct_per_hour=slope30,
                r2_30m=r2_30, pullback_from_10m_high_pct=pullback_pct,
                rebound_2m_pct=rebound2,
            ))

    # BO1: break above a narrow prior 10-minute range. Minute volume is not in
    # the quote tape, so volume confirmation is added later from Schwab candles.
    if len(prices) >= BO1_LOOKBACK_MINUTES + 2:
        prior = prices.iloc[-(BO1_LOOKBACK_MINUTES + 1):-1]
        prior_high = float(prior.max()); prior_low = float(prior.min())
        range_pct = (prior_high / prior_low - 1.0) * 100.0 if prior_low > 0 else math.nan
        breakout_pct = (px / prior_high - 1.0) * 100.0 if prior_high > 0 else math.nan
        if range_pct <= BO1_MAX_RANGE_PCT and breakout_pct >= BO1_BREAK_BUFFER_PCT:
            signals.append(_independent_signal(
                "BO1", sym, ts, px, 1.00, 0.75, "consolidation_breakout",
                prior_range_high=prior_high, prior_range_low=prior_low,
                prior_range_pct=range_pct, breakout_pct=breakout_pct,
            ))

    # OR1: opening-range breakout, deliberately limited to 09:45-10:15 ET so
    # the 50-minute rolling cache always contains the complete opening range.
    if OR1_RANGE_END_MINUTE_ET <= minute_et <= OR1_ENTRY_END_MINUTE_ET:
        opening = work[
            (work["timestamp"].dt.tz_convert(ZoneInfo("America/New_York")).dt.hour == 9)
            & (work["timestamp"].dt.tz_convert(ZoneInfo("America/New_York")).dt.minute >= 30)
            & (work["timestamp"].dt.tz_convert(ZoneInfo("America/New_York")).dt.minute < 45)
        ]
        if len(opening) >= 10:
            or_high = float(opening["price"].max()); or_low = float(opening["price"].min())
            or_range_pct = (or_high / or_low - 1.0) * 100.0 if or_low > 0 else math.nan
            break_pct = (px / or_high - 1.0) * 100.0 if or_high > 0 else math.nan
            if OR1_MIN_RANGE_PCT <= or_range_pct <= OR1_MAX_RANGE_PCT and break_pct >= OR1_BREAK_BUFFER_PCT:
                stop_pct = max(0.50, min(1.00, or_range_pct * 0.50))
                target_pct = max(0.75, min(1.50, or_range_pct))
                signals.append(_independent_signal(
                    "OR1", sym, ts, px, target_pct, stop_pct, "opening_range_breakout",
                    opening_range_high=or_high, opening_range_low=or_low,
                    opening_range_pct=or_range_pct, breakout_pct=break_pct,
                ))

    # RS1: positive 30-minute trend and substantial excess return over SPY.
    if len(prices) >= 31 and spy_30m_return_pct is not None and not math.isnan(ret30):
        excess = ret30 - float(spy_30m_return_pct)
        if ret30 >= RS1_MIN_RETURN_30M_PCT and excess >= RS1_MIN_EXCESS_VS_SPY_PCT and r2_30 >= RS1_MIN_R2:
            signals.append(_independent_signal(
                "RS1", sym, ts, px, 0.90, 0.65, "relative_strength",
                return_30m_pct=ret30, spy_return_30m_pct=float(spy_30m_return_pct),
                excess_return_30m_pct=excess, r2_30m=r2_30,
            ))

    # RS2: same RS1 entry research stream with an alternate exit hypothesis.
    # Paper-only variant; it does not add a scanner or extra quote collection.
    if len(prices) >= 31 and spy_30m_return_pct is not None and not math.isnan(ret30):
        excess = ret30 - float(spy_30m_return_pct)
        if ret30 >= RS1_MIN_RETURN_30M_PCT and excess >= RS1_MIN_EXCESS_VS_SPY_PCT and r2_30 >= RS1_MIN_R2:
            signals.append(_independent_signal(
                "RS2", sym, ts, px, 0.90, 0.65, "relative_strength_exit_variant",
                parent_strategy="RS1",
                exit_model="50pct_rs1_exit_50pct_60m_hold",
                return_30m_pct=ret30, spy_return_30m_pct=float(spy_30m_return_pct),
                excess_return_30m_pct=excess, r2_30m=r2_30,
            ))

    # VE1: break from a compressed 15-minute range.
    if len(prices) >= VE1_COMPRESSION_MINUTES + 2:
        compressed = prices.iloc[-(VE1_COMPRESSION_MINUTES + 1):-1]
        c_high = float(compressed.max()); c_low = float(compressed.min())
        c_range_pct = (c_high / c_low - 1.0) * 100.0 if c_low > 0 else math.nan
        expansion_pct = (px / c_high - 1.0) * 100.0 if c_high > 0 else math.nan
        if c_range_pct <= VE1_MAX_COMPRESSION_RANGE_PCT and expansion_pct >= VE1_BREAK_BUFFER_PCT:
            target_pct = max(0.60, min(1.20, c_range_pct * 1.5))
            signals.append(_independent_signal(
                "VE1", sym, ts, px, target_pct, 0.60, "volatility_expansion",
                compression_range_high=c_high, compression_range_low=c_low,
                compression_range_pct=c_range_pct, expansion_pct=expansion_pct,
            ))

    # RS3: same relative-strength entry, but a tighter prospective payoff
    # geometry than RS1. This is an exit-refinement experiment, not a claim
    # that the thresholds are already optimal.
    if len(prices) >= 31 and spy_30m_return_pct is not None and not math.isnan(ret30):
        excess = ret30 - float(spy_30m_return_pct)
        if ret30 >= RS1_MIN_RETURN_30M_PCT and excess >= RS1_MIN_EXCESS_VS_SPY_PCT and r2_30 >= RS1_MIN_R2:
            signals.append(_independent_signal(
                "RS3", sym, ts, px, 0.60, 0.45, "relative_strength_tighter_exit",
                parent_strategy="RS1", exit_model="tighter_target_and_stop",
                return_30m_pct=ret30, spy_return_30m_pct=float(spy_30m_return_pct),
                excess_return_30m_pct=excess, r2_30m=r2_30,
                forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))

    # MC1: continuation near the recent high after aligned 5m/15m momentum.
    if len(prices) >= 31:
        ret15 = _simple_return_pct(prices.iloc[-16], prices.iloc[-1])
        ret5 = _simple_return_pct(prices.iloc[-6], prices.iloc[-1])
        high10 = float(prices.tail(10).max())
        distance_high = (high10 / px - 1.0) * 100.0 if px > 0 else math.nan
        if (ret15 >= MC1_MIN_RETURN_15M_PCT and ret5 >= MC1_MIN_RETURN_5M_PCT
                and r2_30 >= MC1_MIN_R2_30M
                and distance_high <= MC1_MAX_DISTANCE_FROM_10M_HIGH_PCT):
            signals.append(_independent_signal(
                "MC1", sym, ts, px, 0.80, 0.55, "momentum_continuation",
                return_15m_pct=ret15, return_5m_pct=ret5, r2_30m=r2_30,
                distance_from_10m_high_pct=distance_high,
                forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))

    # TL1: reclaim of an upward 30m regression line after a temporary dip.
    if len(prices) >= 31:
        y = np.log(prices.tail(31).to_numpy(dtype=float))
        x = np.arange(len(y), dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        trend = np.exp(intercept + slope * x)
        prior_gap = (trend[-2] / float(prices.iloc[-2]) - 1.0) * 100.0
        crossed = float(prices.iloc[-2]) < trend[-2] and px >= trend[-1]
        if slope > 0 and r2_30 >= TL1_MIN_R2_30M and prior_gap >= TL1_MIN_PRIOR_GAP_BELOW_TREND_PCT and crossed:
            signals.append(_independent_signal(
                "TL1", sym, ts, px, 0.75, 0.50, "uptrend_line_reclaim",
                r2_30m=r2_30, slope_30m_pct_per_hour=slope30,
                prior_gap_below_trendline_pct=prior_gap,
                trendline_price_now=float(trend[-1]),
                forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))

    # AV1: volatility-adaptive pullback and rebound. Thresholds scale with the
    # symbol's own recent one-minute variation rather than one fixed drop size.
    if len(prices) >= 31:
        returns_1m = prices.tail(31).pct_change().dropna() * 100.0
        sigma = float(returns_1m.std(ddof=0)) if len(returns_1m) >= 10 else math.nan
        high15 = float(prices.tail(16).max())
        low5 = float(prices.tail(6).min())
        drawdown = (high15 / low5 - 1.0) * 100.0 if low5 > 0 else math.nan
        rebound2 = _simple_return_pct(prices.iloc[-3], prices.iloc[-1])
        required_drawdown = max(AV1_MIN_DRAWDOWN_PCT, AV1_VOLATILITY_MULTIPLIER * sigma) if not math.isnan(sigma) else math.inf
        required_rebound = max(AV1_MIN_REBOUND_2M_PCT, 0.5 * sigma) if not math.isnan(sigma) else math.inf
        if slope30 > 0 and drawdown >= required_drawdown and rebound2 >= required_rebound:
            signals.append(_independent_signal(
                "AV1", sym, ts, px, 0.75, 0.60, "volatility_adaptive_rebound",
                recent_sigma_1m_pct=sigma, drawdown_15m_to_5m_low_pct=drawdown,
                required_drawdown_pct=required_drawdown, rebound_2m_pct=rebound2,
                required_rebound_pct=required_rebound,
                forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))

    # TD1: a deliberately time-bounded relative-strength continuation test.
    if (TD1_START_MINUTE_ET <= minute_et <= TD1_END_MINUTE_ET
            and len(prices) >= 31 and spy_30m_return_pct is not None):
        excess = ret30 - float(spy_30m_return_pct)
        ret5 = _simple_return_pct(prices.iloc[-6], prices.iloc[-1])
        if ret30 >= TD1_MIN_RETURN_30M_PCT and excess >= TD1_MIN_EXCESS_VS_SPY_PCT and ret5 > 0:
            signals.append(_independent_signal(
                "TD1", sym, ts, px, 0.75, 0.55, "time_of_day_relative_strength",
                minute_et=minute_et, return_30m_pct=ret30,
                spy_return_30m_pct=float(spy_30m_return_pct), excess_return_30m_pct=excess,
                return_5m_pct=ret5, forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))

    # SH1: decline-shape filter. The second half must be materially less weak
    # than the first half, followed by a positive three-minute turn.
    if len(prices) >= 21:
        w = prices.tail(21).reset_index(drop=True)
        decline20 = (float(w.iloc[0]) / float(w.min()) - 1.0) * 100.0
        first_half = _simple_return_pct(w.iloc[0], w.iloc[10])
        second_half = _simple_return_pct(w.iloc[10], w.iloc[-1])
        rebound3 = _simple_return_pct(w.iloc[-4], w.iloc[-1])
        flattening = abs(second_half) / abs(first_half) if first_half < 0 else math.inf
        if decline20 >= SH1_MIN_DECLINE_20M_PCT and first_half < 0 and flattening <= SH1_MIN_FLATTENING_RATIO and rebound3 > 0:
            signals.append(_independent_signal(
                "SH1", sym, ts, px, 0.70, 0.60, "decline_shape_flattening",
                decline_20m_pct=decline20, first_half_return_pct=first_half,
                second_half_return_pct=second_half, flattening_ratio=flattening,
                rebound_3m_pct=rebound3, forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))

    # CV1: curvature/deceleration. Compare early and late regression slopes.
    if len(prices) >= 21:
        early_slope, early_r2 = fit_log_slope_pct_per_hour(prices.iloc[-21:-10])
        late_slope, late_r2 = fit_log_slope_pct_per_hour(prices.tail(11))
        low20 = float(prices.tail(21).min())
        rebound_low = (px / low20 - 1.0) * 100.0 if low20 > 0 else math.nan
        improvement = late_slope - early_slope
        if early_slope < 0 and improvement >= CV1_MIN_SLOPE_IMPROVEMENT_PCT_PER_HOUR and rebound_low >= CV1_MIN_REBOUND_FROM_LOW_PCT:
            signals.append(_independent_signal(
                "CV1", sym, ts, px, 0.70, 0.55, "selloff_curvature_reversal",
                early_slope_pct_per_hour=early_slope, late_slope_pct_per_hour=late_slope,
                slope_improvement_pct_per_hour=improvement, early_r2=early_r2,
                late_r2=late_r2, rebound_from_20m_low_pct=rebound_low,
                forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))

    # HL1: two distinct swing lows, with the second higher than the first, then
    # a break above the intervening swing high.
    if len(prices) >= 21:
        w = prices.tail(21).reset_index(drop=True)
        local_lows = [i for i in range(1, len(w)-1) if w.iloc[i] <= w.iloc[i-1] and w.iloc[i] < w.iloc[i+1]]
        if len(local_lows) >= 2:
            i1, i2 = local_lows[-2], local_lows[-1]
            if i2 - i1 >= 3:
                low1, low2 = float(w.iloc[i1]), float(w.iloc[i2])
                higher_low_pct = (low2 / low1 - 1.0) * 100.0 if low1 > 0 else math.nan
                intervening_high = float(w.iloc[i1:i2+1].max())
                break_pct = (px / intervening_high - 1.0) * 100.0 if intervening_high > 0 else math.nan
                if higher_low_pct >= HL1_MIN_HIGHER_LOW_PCT and break_pct >= HL1_BREAK_BUFFER_PCT:
                    signals.append(_independent_signal(
                        "HL1", sym, ts, px, 0.80, 0.55, "higher_low_breakout",
                        first_low=low1, second_low=low2, higher_low_pct=higher_low_pct,
                        intervening_high=intervening_high, breakout_pct=break_pct,
                        forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
                    ))

    # VT1: positive 45m trend with price simultaneously near its fitted trend
    # and rolling mean, followed by a short rebound.
    if len(prices) >= 46:
        w45 = prices.tail(46)
        slope45, r2_45 = fit_log_slope_pct_per_hour(w45)
        y45 = np.log(w45.to_numpy(dtype=float)); x45 = np.arange(len(y45), dtype=float)
        s45, i45 = np.polyfit(x45, y45, 1)
        trend_now = float(np.exp(i45 + s45 * x45[-1]))
        mean30 = float(prices.tail(30).mean())
        trend_dist = abs(px / trend_now - 1.0) * 100.0
        mean_dist = abs(px / mean30 - 1.0) * 100.0
        rebound2 = _simple_return_pct(prices.iloc[-3], prices.iloc[-1])
        if (slope45 > 0 and r2_45 >= VT1_MIN_R2_45M
                and trend_dist <= VT1_MAX_CONFLUENCE_DISTANCE_PCT
                and mean_dist <= VT1_MAX_CONFLUENCE_DISTANCE_PCT
                and rebound2 >= VT1_MIN_REBOUND_2M_PCT):
            signals.append(_independent_signal(
                "VT1", sym, ts, px, 0.80, 0.55, "trendline_mean_confluence",
                slope_45m_pct_per_hour=slope45, r2_45m=r2_45,
                trendline_price=trend_now, rolling_mean_30m=mean30,
                distance_to_trendline_pct=trend_dist, distance_to_mean_pct=mean_dist,
                rebound_2m_pct=rebound2, forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))

    # PD1: explicitly isolate a sharp one-minute panic drop followed by a
    # measurable snapback, distinct from the orderly-decline strategies.
    if len(prices) >= 12:
        w = prices.tail(12).reset_index(drop=True)
        minute_returns = w.pct_change().dropna() * 100.0
        worst_pos = int(minute_returns.idxmin())
        worst_drop = -float(minute_returns.loc[worst_pos])
        low_after = float(w.iloc[worst_pos:].min())
        low_pos = int(w.iloc[worst_pos:].idxmin())
        low_age = (len(w) - 1) - low_pos
        rebound_low = (px / low_after - 1.0) * 100.0 if low_after > 0 else math.nan
        rebound2 = _simple_return_pct(w.iloc[-3], w.iloc[-1])
        if (worst_drop >= PD1_MIN_ONE_MINUTE_DROP_PCT and 2 <= low_age <= 8
                and rebound_low >= PD1_MIN_REBOUND_FROM_LOW_PCT and rebound2 > 0):
            signals.append(_independent_signal(
                "PD1", sym, ts, px, 0.85, 0.70, "panic_drop_snapback",
                worst_one_minute_drop_pct=worst_drop, low_age_minutes=low_age,
                rebound_from_low_pct=rebound_low, rebound_2m_pct=rebound2,
                forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))

    # M1-M3: slower selloff exhaustion followed by initial recovery. These
    # strategies are independent of the 3-minute flash detector.
    for strategy_id, cfg in MEDIUM_REVERSAL_CONFIGS.items():
        lookback = int(cfg["lookback_minutes"])
        if len(prices) < lookback + 1:
            continue
        window = prices.tail(lookback + 1).reset_index(drop=True)
        start_price = float(window.iloc[0])
        low_price = float(window.min())
        low_index = int(window.idxmin())
        decline_pct = (start_price / low_price - 1.0) * 100.0 if low_price > 0 else math.nan
        low_age_minutes = (len(window) - 1) - low_index
        rebound_from_low_pct = (px / low_price - 1.0) * 100.0 if low_price > 0 else math.nan
        rebound_2m_pct = _simple_return_pct(window.iloc[-3], window.iloc[-1]) if len(window) >= 3 else math.nan
        one_minute_declines = -(window.pct_change().dropna() * 100.0)
        largest_one_minute_decline_pct = max(0.0, float(one_minute_declines.max())) if not one_minute_declines.empty else 0.0
        largest_minute_share = largest_one_minute_decline_pct / decline_pct if decline_pct > 0 else math.inf
        prior_minute_above_low = float(window.iloc[-2]) > low_price
        if (
            decline_pct >= float(cfg["min_decline_pct"])
            and MEDIUM_REVERSAL_MIN_LOW_AGE_MINUTES <= low_age_minutes <= MEDIUM_REVERSAL_MAX_LOW_AGE_MINUTES
            and rebound_from_low_pct >= float(cfg["min_rebound_from_low_pct"])
            and rebound_2m_pct >= float(cfg["min_rebound_2m_pct"])
            and prior_minute_above_low
            and largest_minute_share <= MEDIUM_REVERSAL_MAX_SINGLE_MINUTE_SHARE
        ):
            signals.append(_independent_signal(
                strategy_id, sym, ts, px, cfg["target_pct"], cfg["stop_pct"],
                f"medium_reversal_{lookback}m",
                lookback_minutes=lookback, decline_from_window_start_to_low_pct=decline_pct,
                window_start_price=start_price, window_low_price=low_price,
                low_age_minutes=low_age_minutes, rebound_from_low_pct=rebound_from_low_pct,
                rebound_2m_pct=rebound_2m_pct,
                largest_one_minute_decline_pct=largest_one_minute_decline_pct,
                largest_minute_share_of_decline=largest_minute_share,
            ))

    # VR1: price was meaningfully below a rolling 30-minute VWAP proxy (the
    # minute-price mean available in the tape), then crossed and held above it.
    # The exact proxy is clearly labelled rather than misrepresented as volume VWAP.
    if len(prices) >= 31:
        rolling = prices.tail(31)
        proxy = float(rolling.iloc[:-2].mean())
        historical_low = float(rolling.iloc[:-2].min())
        depth_pct = (proxy / historical_low - 1.0) * 100.0 if historical_low > 0 else math.nan
        held_above = float(rolling.iloc[-2]) >= proxy and float(rolling.iloc[-1]) >= proxy
        crossed = float(rolling.iloc[-3]) < proxy <= float(rolling.iloc[-2])
        if depth_pct >= VR1_MIN_DEPTH_BELOW_VWAP_PCT and crossed and held_above:
            signals.append(_independent_signal(
                "VR1", sym, ts, px, 0.75, 0.45, "rolling_mean_reclaim_proxy",
                rolling_mean_30m=proxy, prior_depth_below_proxy_pct=depth_pct,
                confirmation_minutes=VR1_HOLD_MINUTES,
            ))


    # EMA1: fresh 9/21 bullish EMA crossover, confirmed by rising minute volume.
    if len(prices) >= EMA1_SLOW_SPAN + 3:
        fast = _ema(prices, EMA1_FAST_SPAN)
        slow = _ema(prices, EMA1_SLOW_SPAN)
        crossed_now = float(fast.iloc[-2]) <= float(slow.iloc[-2]) and float(fast.iloc[-1]) > float(slow.iloc[-1])
        if crossed_now:
            volume_ratio = _confirm_recent_volume_ratio(sym)
            if volume_ratio is not None and volume_ratio >= EMA1_MIN_VOLUME_RATIO:
                signals.append(_independent_signal(
                    "EMA1", sym, ts, px, 0.75, 0.55, "ema_9_21_bullish_crossover",
                    ema_9=float(fast.iloc[-1]), ema_21=float(slow.iloc[-1]),
                    prior_ema_9=float(fast.iloc[-2]), prior_ema_21=float(slow.iloc[-2]),
                    latest_volume_ratio=volume_ratio,
                    minimum_volume_ratio=EMA1_MIN_VOLUME_RATIO,
                    forward_start_utc=EMA_RESEARCH_FORWARD_START_UTC,
                ))

    # EMA2: price pulls back close to a rising 20 EMA, then turns upward.
    if len(prices) >= EMA2_SPAN + 4:
        ema20 = _ema(prices, EMA2_SPAN)
        ema_rising = float(ema20.iloc[-1]) > float(ema20.iloc[-4])
        prior_distance = abs(float(prices.iloc[-2]) / float(ema20.iloc[-2]) - 1.0) * 100.0
        bounce2 = _simple_return_pct(prices.iloc[-3], prices.iloc[-1])
        reclaimed = float(prices.iloc[-2]) <= float(ema20.iloc[-2]) and px > float(ema20.iloc[-1])
        if (
            ema_rising
            and prior_distance <= EMA2_MAX_PULLBACK_DISTANCE_PCT
            and bounce2 >= EMA2_MIN_BOUNCE_2M_PCT
            and reclaimed
        ):
            signals.append(_independent_signal(
                "EMA2", sym, ts, px, 0.75, 0.50, "rising_ema20_pullback_bounce",
                ema_20=float(ema20.iloc[-1]),
                ema_20_change_3m_pct=_simple_return_pct(ema20.iloc[-4], ema20.iloc[-1]),
                prior_distance_from_ema_pct=prior_distance,
                rebound_2m_pct=bounce2,
                forward_start_utc=EMA_RESEARCH_FORWARD_START_UTC,
            ))

    # EMA3: sustained 9 > 21 > 50 alignment followed by a recent-high breakout.
    if len(prices) >= EMA3_SLOW_SPAN + EMA3_ALIGNMENT_MINUTES + 2:
        ema9 = _ema(prices, EMA3_FAST_SPAN)
        ema21 = _ema(prices, EMA3_MID_SPAN)
        ema50 = _ema(prices, EMA3_SLOW_SPAN)
        aligned = (
            (ema9.tail(EMA3_ALIGNMENT_MINUTES) > ema21.tail(EMA3_ALIGNMENT_MINUTES)).all()
            and (ema21.tail(EMA3_ALIGNMENT_MINUTES) > ema50.tail(EMA3_ALIGNMENT_MINUTES)).all()
        )
        prior_high = float(prices.iloc[-(EMA3_BREAKOUT_LOOKBACK_MINUTES + 1):-1].max())
        breakout_pct = (px / prior_high - 1.0) * 100.0 if prior_high > 0 else math.nan
        if aligned and breakout_pct >= EMA3_BREAK_BUFFER_PCT:
            signals.append(_independent_signal(
                "EMA3", sym, ts, px, 0.90, 0.60, "ema_alignment_breakout",
                ema_9=float(ema9.iloc[-1]), ema_21=float(ema21.iloc[-1]), ema_50=float(ema50.iloc[-1]),
                alignment_minutes=EMA3_ALIGNMENT_MINUTES,
                prior_high=prior_high, breakout_pct=breakout_pct,
                forward_start_utc=EMA_RESEARCH_FORWARD_START_UTC,
            ))

    # SMA1: 20 SMA crosses above 50 SMA and remains above for two completed minutes.
    if len(prices) >= SMA1_SLOW_WINDOW + SMA1_CONFIRM_MINUTES + 1:
        sma20 = prices.rolling(SMA1_FAST_WINDOW).mean()
        sma50 = prices.rolling(SMA1_SLOW_WINDOW).mean()
        confirmed = (
            float(sma20.iloc[-3]) <= float(sma50.iloc[-3])
            and float(sma20.iloc[-2]) > float(sma50.iloc[-2])
            and float(sma20.iloc[-1]) > float(sma50.iloc[-1])
        )
        if confirmed:
            signals.append(_independent_signal(
                "SMA1", sym, ts, px, 0.85, 0.60, "sma_20_50_bullish_crossover",
                sma_20=float(sma20.iloc[-1]), sma_50=float(sma50.iloc[-1]),
                confirmation_minutes=SMA1_CONFIRM_MINUTES,
                forward_start_utc=EMA_RESEARCH_FORWARD_START_UTC,
            ))

    # VWEMA1: price above a rolling VWAP proxy and 20 EMA with positive momentum.
    # The quote tape has no volume, so the rolling mean is explicitly labelled a
    # price-mean proxy rather than true VWAP.
    if len(prices) >= 31:
        ema20 = _ema(prices, VWEMA1_EMA_SPAN)
        vwap_proxy = float(prices.tail(30).mean())
        above_proxy_pct = (px / vwap_proxy - 1.0) * 100.0 if vwap_proxy > 0 else math.nan
        ret15 = _simple_return_pct(prices.iloc[-16], prices.iloc[-1])
        if (
            px > float(ema20.iloc[-1])
            and above_proxy_pct >= VWEMA1_MIN_PRICE_ABOVE_VWAP_PCT
            and ret15 >= VWEMA1_MIN_RETURN_15M_PCT
            and float(ema20.iloc[-1]) > float(ema20.iloc[-4])
        ):
            signals.append(_independent_signal(
                "VWEMA1", sym, ts, px, 0.80, 0.55, "price_above_mean_proxy_and_ema20",
                ema_20=float(ema20.iloc[-1]), rolling_price_mean_30m=vwap_proxy,
                distance_above_price_mean_pct=above_proxy_pct,
                return_15m_pct=ret15,
                proxy_note="rolling price mean; not true volume-weighted VWAP",
                forward_start_utc=EMA_RESEARCH_FORWARD_START_UTC,
            ))

    return signals


def main():
    print("🚀 V15 FLASH-DIP RUNNER ONLINE — A LIVE + B/D/H PAPER", flush=True)
    print(f"PRE={PRE_CRASH_TREND_MINUTES}m FLASH={FLASH_WINDOW_MINUTES}m DROP={FLASH_DROP_PCT}-{MAX_FLASH_DROP_PCT}% TARGET={RECOVERY_TARGET_FRACTION} STOP={STOP_LOSS_FRACTION_BELOW_ENTRY}", flush=True)

    trader = make_trader()
    last_trading_token_touch = 0
    last_market_token_touch = 0
    positions = load_positions()
    print(f"LOADED_POSITIONS={list(positions.keys())}", flush=True)

    # In-memory research tracker for NEAR_MISS forward returns.
    near_miss_tracker = {}
    near_miss_logged = set()  # (market_day, strategy_id, symbol)
    near_miss_logged_day = None

    # Symbols that met the full signal but are waiting for a 0.10% rebound
    # from the lowest live price observed after qualification.
    pending_entries = {strategy_id: {} for strategy_id in STRATEGY_CONFIGS}
    last_flash_signature = {strategy_id: {} for strategy_id in STRATEGY_CONFIGS}

    # Native independent-strategy signals are deduplicated by emitted minute and
    # also receive a per-symbol cooldown to avoid repeatedly entering one trend.
    independent_last_signal = {}
    independent_dedupe_day = None

    while True:
        try:
            now_ts = time.time()

            market_token_path = "/data/schwab_token.json"
            market_min_left = token_minutes_left(market_token_path)

            if market_min_left < 20 and now_ts - last_market_token_touch >= 60:
                last_market_token_touch = now_ts
                try:
                    from schwab.auth import client_from_token_file
                    market_client = client_from_token_file(
                        market_token_path,
                        os.environ["SCHWAB_MARKET_APP_KEY"],
                        os.environ["SCHWAB_MARKET_SECRET"],
                    )
                    r = market_client.get_quotes(["VOO"])
                    print(f"MARKET_TOKEN_REFRESH status={getattr(r, 'status_code', 'NA')} before_min_left={market_min_left:.1f}", flush=True)
                except Exception as e:
                    print(f"MARKET_TOKEN_REFRESH error: {type(e).__name__}: {e}", flush=True)

            trade_token_path = "/data/schwab_trade_token.json"
            trade_min_left = token_minutes_left(trade_token_path)

            if trade_min_left < 20 and now_ts - last_trading_token_touch >= 60:
                last_trading_token_touch = now_ts
                try:
                    after_min_left = explicit_refresh_schwab_token(
                        trade_token_path,
                        os.environ["SCHWAB_TRADING_APP_KEY"],
                        os.environ["SCHWAB_TRADING_SECRET"],
                    )
                    refreshed = make_trader()
                    trader = refreshed
                    print(f"TRADING_TOKEN_REFRESH OK before_min_left={trade_min_left:.1f} after_min_left={after_min_left:.1f}", flush=True)
                except Exception as e:
                    print(f"TRADING_TOKEN_REFRESH error: {type(e).__name__}: {e}", flush=True)

            df = quote_source.read_data()
            if df is None or df.empty:
                print("No tape yet.", flush=True)
                time.sleep(POLL_SECONDS)
                continue

            prices_now = latest_prices(df)
            manage_exits(trader, positions, prices_now)

            now_utc = datetime.now(timezone.utc)
            market_day = now_utc.astimezone(ZoneInfo("America/New_York")).date().isoformat()
            if market_day != near_miss_logged_day:
                near_miss_logged.clear()
                near_miss_logged_day = market_day

            # Do not generate, record, or paper-track signals/near misses
            # outside regular trading hours. Broker-side exits remain active,
            # and manage_exits() above still handles the 15:55 ET flattening.
            if not is_regular_market_hours_et():
                write_bot_output(status="outside_rth", triggers=[], nearest=[])
                time.sleep(POLL_SECONDS)
                continue

            # Fill forward outcomes for tracked near misses.
            for key, rec in list(near_miss_tracker.items()):
                sym = rec["symbol"]
                px = prices_now.get(sym)
                if not px or not rec.get("entry_price"):
                    continue

                age_min = (now_utc - rec["timestamp"]).total_seconds() / 60.0

                for horizon in (15, 30, 60):
                    field = f"ret_{horizon}m"
                    if age_min >= horizon and field not in rec:
                        ret = (px / rec["entry_price"] - 1) * 100
                        rec[field] = ret
                        rec[f"price_{horizon}m"] = px
                        append_strategy_event(
                            rec.get("strategy_id", STRATEGY_A),
                            f"NEAR_MISS_OUTCOME_{horizon}M",
                            symbol=sym,
                            original_timestamp=rec["timestamp"].isoformat(),
                            entry_price=rec["entry_price"],
                            outcome_price=px,
                            return_pct=ret,
                            candidate=rec["candidate"],
                        )

            events = []
            near_events = []
            independent_events = []

            if market_day != independent_dedupe_day:
                independent_last_signal.clear()
                independent_dedupe_day = market_day

            spy_30m_return_pct = None
            try:
                spy_group = df[df["symbol"].astype(str) == "SPY"].sort_values("timestamp")
                if len(spy_group) >= 31:
                    spy_prices = spy_group["price"].astype(float).tail(31)
                    spy_30m_return_pct = _simple_return_pct(spy_prices.iloc[0], spy_prices.iloc[-1])
            except Exception:
                spy_30m_return_pct = None

            scan_stats = {
                "symbols_seen": 0,
                "positions_skipped": 0,
                "triggers": 0,
                "empty_minute_series": 0,
                "insufficient_history": 0,
                "missing_minutes": 0,
                "invalid_prices": 0,
                "calculation_errors": 0,
                "near_candidates": 0,
            }
            scan_error_samples = []

            for sym, g in df.groupby("symbol"):
                scan_stats["symbols_seen"] += 1
                if sym in positions:
                    scan_stats["positions_skipped"] += 1
                    continue

                current_price = prices_now.get(sym)

                # Evaluate each strategy independently against the same market price.
                strategies_processed_pending = set()
                for strategy_id, cfg in STRATEGY_CONFIGS.items():
                    pending = pending_entries[strategy_id].get(sym)
                    if pending is None:
                        continue
                    strategies_processed_pending.add(strategy_id)
                    if not current_price or current_price <= 0:
                        continue

                    px = float(current_price)
                    age_seconds = (now_utc - pending["created_at"]).total_seconds()
                    running_low = min(float(pending["lowest_price"]), px)
                    pending["lowest_price"] = running_low
                    rebound_fraction = (px / running_low) - 1.0

                    if age_seconds >= PENDING_REBOUND_TIMEOUT_SECONDS:
                        append_strategy_event(strategy_id, "PENDING_REBOUND_CANCELLED_TIMEOUT",
                            symbol=sym, current_price=px, lowest_price=running_low,
                            waiting_seconds=age_seconds, rebound_pct=rebound_fraction * 100)
                        pending_entries[strategy_id].pop(sym, None)
                        continue

                    if rebound_fraction < cfg["rebound_confirmation_pct"]:
                        continue

                    confirmed_event = refresh_event_for_entry(
                        pending["initial_signal"], px, strategy_id
                    )
                    original_flash_start = float(confirmed_event["flash_start_price"])
                    full_recovery_distance = original_flash_start - running_low
                    recovery_fraction = (
                        (px - running_low) / full_recovery_distance
                        if full_recovery_distance > 0 else float("inf")
                    )
                    confirmed_event.update({
                        "pending_created_at": pending["created_at"].isoformat(),
                        "confirmation_wait_seconds": age_seconds,
                        "running_low_price": running_low,
                        "actual_rebound_pct": rebound_fraction * 100,
                        "recovery_fraction_at_entry": recovery_fraction,
                    })
                    valid, reject_reason = validate_confirmed_entry(confirmed_event)
                    if not valid:
                        append_strategy_event(strategy_id, "PENDING_REBOUND_CANCELLED_OVERSHOOT",
                            symbol=sym, reason=reject_reason, current_price=px,
                            original_target_price=confirmed_event.get("original_target_price"),
                            remaining_upside_pct=confirmed_event.get("remaining_upside_pct"),
                            recovery_fraction_at_entry=recovery_fraction, signal=confirmed_event)
                        pending_entries[strategy_id].pop(sym, None)
                        continue

                    confirmed_event.update(fetch_rebound_volume_metrics(
                        sym, pending["created_at"], confirmed_event.get("avg_volume_1m_pre30")
                    ))
                    events.append(confirmed_event)
                    scan_stats["triggers"] += 1
                    pending_entries[strategy_id].pop(sym, None)
                    append_strategy_event(strategy_id, "REBOUND_CONFIRMED",
                        symbol=sym, lowest_price=running_low, entry_price=px,
                        rebound_pct=rebound_fraction * 100, waiting_seconds=age_seconds,
                        recovery_fraction_at_entry=recovery_fraction, signal=confirmed_event)

                # Independently scan this symbol for non-mean-reversion strategy
                # families. These emit paper SIGNAL events directly and never place orders.
                try:
                    for independent in detect_independent_signals(sym, g, spy_30m_return_pct):
                        strategy_id = independent["strategy_id"]
                        emitted_ts = pd.Timestamp(independent["timestamp"])
                        dedupe_key = (market_day, strategy_id, str(sym))
                        prior_ts = independent_last_signal.get(dedupe_key)
                        if prior_ts is not None:
                            age_minutes = (emitted_ts - prior_ts).total_seconds() / 60.0
                            if age_minutes < INDEPENDENT_COOLDOWN_MINUTES:
                                continue
                        independent_last_signal[dedupe_key] = emitted_ts
                        independent_events.append(independent)
                        append_strategy_event(
                            strategy_id,
                            "SIGNAL",
                            symbol=sym,
                            signal=independent,
                            thresholds={
                                "INDEPENDENT_FORWARD_START_UTC": INDEPENDENT_FORWARD_START_UTC,
                                "INDEPENDENT_COOLDOWN_MINUTES": INDEPENDENT_COOLDOWN_MINUTES,
                                "LIVE_ORDER_PLACEMENT": False,
                            },
                        )
                except Exception as ex:
                    scan_stats["calculation_errors"] += 1
                    if len(scan_error_samples) < 5:
                        scan_error_samples.append(
                            f"independent symbol={sym} type={type(ex).__name__} error={ex}"
                        )

                # Detect using the lowest configured threshold, then admit only the
                # strategies whose own flash threshold is satisfied.
                event = detect_latest_flash(
                    sym, g, min(cfg["flash_drop_pct"] for cfg in STRATEGY_CONFIGS.values())
                )

                if event:
                    if not current_price or current_price <= 0:
                        continue

                    current_price = float(current_price)
                    event.update(fetch_flash_volume_metrics(sym))
                    if (
                        event.get("flash_dollar_volume_3m") is None
                        or event["flash_dollar_volume_3m"] < MIN_FLASH_DOLLAR_VOLUME_3M
                    ):
                        for strategy_id, cfg in STRATEGY_CONFIGS.items():
                            if strategy_accepts_flash(strategy_id, event):
                                append_strategy_event(
                                    strategy_id,
                                    "LIQUIDITY_REJECTED",
                                    symbol=sym,
                                    flash_dollar_volume_3m=event.get("flash_dollar_volume_3m"),
                                    minimum_required=MIN_FLASH_DOLLAR_VOLUME_3M,
                                    signal=event,
                                )
                        continue
                    flash_signature = event.get("signal_window_end")
                    created_any = False
                    for strategy_id, cfg in STRATEGY_CONFIGS.items():
                        if strategy_id in strategies_processed_pending:
                            continue
                        if not strategy_accepts_flash(strategy_id, event):
                            continue
                        if last_flash_signature[strategy_id].get(sym) == flash_signature:
                            continue
                        strategy_event = dict(event)
                        strategy_event["strategy_id"] = strategy_id
                        strategy_event["strategy_flash_drop_threshold_pct"] = cfg["flash_drop_pct"]
                        strategy_event["stop_price"] = current_price * (1 - cfg["stop_loss_fraction"])
                        pending_entries[strategy_id][sym] = {
                            "created_at": now_utc,
                            "lowest_price": current_price,
                            "initial_signal": strategy_event,
                        }
                        last_flash_signature[strategy_id][sym] = flash_signature
                        append_strategy_event(strategy_id, "PENDING_REBOUND_CREATED",
                            symbol=sym, current_price=current_price,
                            required_rebound_pct=cfg["rebound_confirmation_pct"] * 100,
                            timeout_seconds=PENDING_REBOUND_TIMEOUT_SECONDS, signal=strategy_event)
                        created_any = True
                    if created_any or strategies_processed_pending:
                        continue
                else:
                    try:
                        prices = minute_prices(g)

                        if prices.empty:
                            scan_stats["empty_minute_series"] += 1
                            continue

                        needed = PRE_CRASH_TREND_MINUTES + FLASH_WINDOW_MINUTES + 1

                        if len(prices) < needed:
                            scan_stats["insufficient_history"] += 1
                            continue

                        window = prices.iloc[-needed:]

                        latest_minute = window.index[-1]
                        now_minute_utc = pd.Timestamp.now(tz="UTC")
                        if latest_minute.tzinfo is None:
                            latest_minute = latest_minute.tz_localize("UTC")
                        else:
                            latest_minute = latest_minute.tz_convert("UTC")
                        if (
                            now_minute_utc - latest_minute
                        ).total_seconds() > MAX_QUOTE_AGE_SECONDS:
                            scan_stats["insufficient_history"] += 1
                            continue

                        # Do not score a near miss across missing minutes.
                        missing_count = int(window.isna().sum())
                        if missing_count:
                            scan_stats["missing_minutes"] += 1
                            continue

                        pre = window.iloc[:PRE_CRASH_TREND_MINUTES + 1]
                        flash = window.iloc[-(FLASH_WINDOW_MINUTES + 1):]

                        flash_start = float(flash.iloc[0])
                        flash_end = float(flash.iloc[-1])
                        pre_start = float(pre.iloc[0]) if len(pre) else 0
                        pre_end = float(pre.iloc[-1]) if len(pre) else 0

                        if flash_start > 0 and flash_end > 0 and pre_start > 0:
                            pre_return_pct = ((pre_end / pre_start) - 1) * 100
                            pre_slope_pct_per_hour, pre_r2 = fit_log_slope_pct_per_hour(pre)
                            flash_drop_pct = ((flash_start - flash_end) / flash_start) * 100
                            gap = FLASH_DROP_PCT - flash_drop_pct

                            pass_pre_return = pre_return_pct >= MIN_PRE_CRASH_RETURN_PCT
                            pass_pre_slope = (
                                not math.isnan(pre_slope_pct_per_hour)
                                and pre_slope_pct_per_hour >= MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR
                            )
                            pass_flash = FLASH_DROP_PCT <= flash_drop_pct <= MAX_FLASH_DROP_PCT

                            failed = []
                            if not pass_pre_return:
                                failed.append("pre_return")
                            if not pass_pre_slope:
                                failed.append("pre_slope")
                            if not pass_flash:
                                failed.append("flash_drop")

                            # Combined "nearest miss" score across all required dimensions.
                            # Lower score = closer to becoming a true trigger.
                            flash_penalty = max(0.0, FLASH_DROP_PCT - flash_drop_pct) / max(FLASH_DROP_PCT, 1e-9)
                            pre_ret_penalty = max(0.0, MIN_PRE_CRASH_RETURN_PCT - pre_return_pct) / max(MIN_PRE_CRASH_RETURN_PCT, 1e-9)
                            pre_slope_penalty = max(0.0, MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR - pre_slope_pct_per_hour) / max(MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR, 1e-9)

                            miss_score = flash_penalty + pre_ret_penalty + pre_slope_penalty

                            near_events.append({
                                "symbol": sym,
                                "flash_drop_pct": flash_drop_pct,
                                "gap": gap,
                                "miss_score": miss_score,
                                "flash_penalty": flash_penalty,
                                "pre_ret_penalty": pre_ret_penalty,
                                "pre_slope_penalty": pre_slope_penalty,
                                "price": flash_end,
                                "pre_return_pct": pre_return_pct,
                                "pre_slope_pct_per_hour": pre_slope_pct_per_hour,
                                "pre_r2": pre_r2,
                                "pass_pre_return": pass_pre_return,
                                "pass_pre_slope": pass_pre_slope,
                                "pass_flash": pass_flash,
                                "failed": ",".join(failed) if failed else "none",
                            })
                            scan_stats["near_candidates"] += 1
                        else:
                            scan_stats["invalid_prices"] += 1

                    except Exception as ex:
                        scan_stats["calculation_errors"] += 1
                        if len(scan_error_samples) < 5:
                            scan_error_samples.append(
                                f"symbol={sym} type={type(ex).__name__} error={ex}"
                            )

            print(
                "SCAN_SUMMARY "
                f"symbols_seen={scan_stats['symbols_seen']} "
                f"positions_skipped={scan_stats['positions_skipped']} "
                f"triggers={scan_stats['triggers']} "
                f"independent_signals={len(independent_events)} "
                f"near_candidates={scan_stats['near_candidates']} "
                f"empty_minute_series={scan_stats['empty_minute_series']} "
                f"insufficient_history={scan_stats['insufficient_history']} "
                f"missing_minutes={scan_stats['missing_minutes']} "
                f"invalid_prices={scan_stats['invalid_prices']} "
                f"calculation_errors={scan_stats['calculation_errors']}",
                flush=True,
            )

            for error_sample in scan_error_samples:
                print(f"SCAN_ERROR_SAMPLE {error_sample}", flush=True)

            if not allow_new_entries_now():
                for strategy_id, strategy_pending in pending_entries.items():
                    for pending_sym, pending in list(strategy_pending.items()):
                        append_strategy_event(strategy_id, "PENDING_REBOUND_CANCELLED_ENTRY_CUTOFF",
                            symbol=pending_sym, lowest_price=pending.get("lowest_price"))
                    strategy_pending.clear()

            events.sort(key=lambda e: e["flash_drop_pct"], reverse=True)
            events_a = [e for e in events if e.get("strategy_id") == STRATEGY_A]
            events_b = [e for e in events if e.get("strategy_id") == STRATEGY_B]
            events_d = [e for e in events if e.get("strategy_id") == STRATEGY_D]
            events_h = [e for e in events if e.get("strategy_id") == STRATEGY_H]

            # Prospective threshold-defined near-miss populations. Log every first
            # qualifying symbol/day observation, regardless of whether other symbols
            # produced full signals in the same scan. This replaces daily top-5 sampling.
            def log_threshold_candidate(strategy_id, candidate, flash_threshold, extra_thresholds=None):
                try:
                    score = float(candidate.get("miss_score", 999))
                except (TypeError, ValueError):
                    return
                if not (0.0 < score <= NEAR_MISS_SCORE_CUTOFF):
                    return
                symbol = str(candidate.get("symbol") or "").upper()
                dedupe_key = (market_day, strategy_id, symbol)
                if not symbol or dedupe_key in near_miss_logged:
                    return
                near_miss_logged.add(dedupe_key)
                candidate = dict(candidate)
                candidate["candidate_cutoff"] = NEAR_MISS_SCORE_CUTOFF
                candidate["candidate_definition"] = "0 < miss_score <= cutoff"
                thresholds = {
                    "NEAR_MISS_SCORE_CUTOFF": NEAR_MISS_SCORE_CUTOFF,
                    "FLASH_DROP_PCT": flash_threshold,
                    "MAX_FLASH_DROP_PCT": STRATEGY_CONFIGS[strategy_id].get("max_flash_drop_pct", MAX_FLASH_DROP_PCT),
                    "MIN_PRE_CRASH_RETURN_PCT": MIN_PRE_CRASH_RETURN_PCT,
                    "MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR": MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR,
                }
                thresholds.update(extra_thresholds or {})
                append_strategy_event(strategy_id, "NEAR_MISS", symbol=symbol, candidate=candidate, thresholds=thresholds)

                tracker_key = f"{strategy_id}|{symbol}|{now_utc.isoformat()}"
                near_miss_tracker[tracker_key] = {
                    "timestamp": now_utc,
                    "symbol": symbol,
                    "entry_price": float(candidate.get("price", 0) or 0),
                    "candidate": candidate,
                    "strategy_id": strategy_id,
                }

            # A and B share the same candidate score/entry boundary.
            for candidate in near_events:
                log_threshold_candidate(STRATEGY_A, candidate, FLASH_DROP_PCT)
                log_threshold_candidate(STRATEGY_B, candidate, FLASH_DROP_PCT)

                # Strategy D changes only the flash threshold to 0.90%.
                d = dict(candidate)
                d_threshold = STRATEGY_CONFIGS[STRATEGY_D]["flash_drop_pct"]
                d["gap"] = d_threshold - float(d.get("flash_drop_pct", 0) or 0)
                d["pass_flash"] = d_threshold <= float(d.get("flash_drop_pct", 0) or 0) <= MAX_FLASH_DROP_PCT
                d["flash_penalty"] = max(0.0, d_threshold - float(d.get("flash_drop_pct", 0) or 0)) / max(d_threshold, 1e-9)
                d["miss_score"] = d["flash_penalty"] + float(d.get("pre_ret_penalty", 0) or 0) + float(d.get("pre_slope_penalty", 0) or 0)
                log_threshold_candidate(STRATEGY_D, d, d_threshold)

                # H adds both lower/upper boundary filters and pre-trend quality.
                h = dict(candidate)
                drop = float(h.get("flash_drop_pct", 0) or 0)
                slope = float(h.get("pre_slope_pct_per_hour", 0) or 0)
                r2 = float(h.get("pre_r2", 0) or 0)
                h_low_flash = max(0.0, STRATEGY_H_MIN_FLASH_DROP_PCT - drop) / max(STRATEGY_H_MIN_FLASH_DROP_PCT, 1e-9)
                h_high_flash = max(0.0, drop - STRATEGY_H_MAX_FLASH_DROP_PCT) / max(STRATEGY_H_MAX_FLASH_DROP_PCT, 1e-9)
                h_high_slope = max(0.0, slope - STRATEGY_H_MAX_PRE_SLOPE_PCT_PER_HOUR) / max(STRATEGY_H_MAX_PRE_SLOPE_PCT_PER_HOUR, 1e-9)
                h_r2 = max(0.0, STRATEGY_H_MIN_PRE_R2 - r2) / max(STRATEGY_H_MIN_PRE_R2, 1e-9)
                h["flash_penalty"] = h_low_flash + h_high_flash
                h["pre_slope_max_penalty"] = h_high_slope
                h["pre_r2_penalty"] = h_r2
                h["miss_score"] = h["flash_penalty"] + float(h.get("pre_ret_penalty", 0) or 0) + float(h.get("pre_slope_penalty", 0) or 0) + h_high_slope + h_r2
                log_threshold_candidate(
                    STRATEGY_H, h, STRATEGY_H_MIN_FLASH_DROP_PCT,
                    extra_thresholds={
                        "MIN_PRE_R2": STRATEGY_H_MIN_PRE_R2,
                        "MAX_PRE_CRASH_SLOPE_PCT_PER_HOUR": STRATEGY_H_MAX_PRE_SLOPE_PCT_PER_HOUR,
                    },
                )

            if events:
                print("=== EXACT V14 FLASH TRIGGERS ===", flush=True)
                for e in events[:10]:
                    print(
                        f"TRIGGER: {e['symbol']} flash_drop={e['flash_drop_pct']:.2f}% "
                        f"pre_return={e['pre_return_pct']:.2f}% pre_slope={e['pre_slope_pct_per_hour']:.2f}%/hr "
                        f"entry={e['entry_price']:.2f} flash_start={e['flash_start_price']:.2f} "
                        f"target={e['target_price']:.2f} stop={e['stop_price']:.2f}",
                        flush=True
                    )

                write_bot_output(status="trigger", triggers=events_a[:10], nearest=[])

                # Strict full-detail ledger: record every threshold-passing signal,
                # independent of whether we later attempt an order.
                for e in events:
                    append_strategy_event(
                        e.get("strategy_id", STRATEGY_A),
                        "SIGNAL",
                        symbol=e.get("symbol"),
                        signal=e,
                        thresholds={
                            "FLASH_DROP_PCT": STRATEGY_CONFIGS[e.get("strategy_id", STRATEGY_A)]["flash_drop_pct"],
                            "MAX_FLASH_DROP_PCT": STRATEGY_CONFIGS[e.get("strategy_id", STRATEGY_A)].get("max_flash_drop_pct", MAX_FLASH_DROP_PCT),
                            "MIN_PRE_CRASH_RETURN_PCT": MIN_PRE_CRASH_RETURN_PCT,
                            "MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR": MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR,
                            "MIN_PRE_R2": STRATEGY_CONFIGS[e.get("strategy_id", STRATEGY_A)].get("min_pre_r2"),
                            "MAX_PRE_CRASH_SLOPE_PCT_PER_HOUR": STRATEGY_CONFIGS[e.get("strategy_id", STRATEGY_A)].get("max_pre_slope_pct_per_hour"),
                            "MIN_REMAINING_UPSIDE_PCT": STRATEGY_CONFIGS[e.get("strategy_id", STRATEGY_A)].get("min_remaining_upside_pct", MIN_REMAINING_UPSIDE_PCT),
                            "RECOVERY_TARGET_FRACTION": RECOVERY_TARGET_FRACTION,
                            "STOP_LOSS_FRACTION_BELOW_ENTRY": STRATEGY_CONFIGS[e.get("strategy_id", STRATEGY_A)]["stop_loss_fraction"],
                            "EOD_EXIT_HOUR_ET": EOD_EXIT_HOUR_ET,
                            "EOD_EXIT_MINUTE_ET": EOD_EXIT_MINUTE_ET,
                            "QTY": QTY,
                            "REBOUND_CONFIRMATION_PCT": STRATEGY_CONFIGS[e.get("strategy_id", STRATEGY_A)]["rebound_confirmation_pct"],
                        },
                    )

                for e in events_a:
                    sym = e["symbol"]

                    if len(attempted) >= MAX_ORDER_ATTEMPTS_PER_BOOT:
                        print("MAX_ORDER_ATTEMPTS_PER_BOOT reached.", flush=True)
                        break

                    if sym in attempted or sym in positions:
                        continue

                    if not is_regular_market_hours_et():
                        print(f"ORDER_BLOCKED_OUTSIDE_RTH {sym}", flush=True)
                        append_bot_event("ORDER_BLOCKED_OUTSIDE_RTH", symbol=sym, signal=e)
                        continue

                    if not allow_new_entries_now():
                        print(f"ORDER_BLOCKED_AFTER_ENTRY_CUTOFF {sym}", flush=True)
                        append_bot_event(
                            "ORDER_BLOCKED_AFTER_ENTRY_CUTOFF",
                            symbol=sym,
                            signal=e,
                        )
                        continue

                    attempted.add(sym)

                    buy_limit_price = round(e["entry_price"] * (1 + BUY_LIMIT_BUFFER_PCT), 2)

                    print(
                        f"ENTRY_TRIGGER_OCO_ATTEMPT {sym} qty={QTY} "
                        f"buy_limit={buy_limit_price:.2f} target={e['target_price']:.2f} stop={e['stop_price']:.2f}",
                        flush=True
                    )

                    append_bot_event(
                        "ENTRY_TRIGGER_OCO_ATTEMPT",
                        symbol=sym,
                        qty=QTY,
                        buy_limit_price=buy_limit_price,
                        target_price=e["target_price"],
                        stop_price=e["stop_price"],
                        signal=e,
                    )

                    try:
                        resp = trader.place_entry_trigger_oco_order(
                            sym,
                            qty=QTY,
                            buy_limit_price=buy_limit_price,
                            target_price=e["target_price"],
                            stop_price=e["stop_price"],
                        )
                        print(f"ENTRY_TRIGGER_OCO_RESPONSE {sym}: {resp}", flush=True)
                        append_bot_event(
                            "ENTRY_TRIGGER_OCO_RESPONSE",
                            symbol=sym,
                            qty=QTY,
                            buy_limit_price=buy_limit_price,
                            target_price=e["target_price"],
                            stop_price=e["stop_price"],
                            response=resp,
                            signal=e,
                        )
                    except Exception as ex:
                        resp = {"ok": False, "error": str(ex), "exception_type": type(ex).__name__}
                        print(f"ENTRY_TRIGGER_OCO_ERROR {sym}: {type(ex).__name__}: {ex}", flush=True)
                        append_bot_event(
                            "ENTRY_TRIGGER_OCO_ERROR",
                            symbol=sym,
                            qty=QTY,
                            buy_limit_price=buy_limit_price,
                            target_price=e["target_price"],
                            stop_price=e["stop_price"],
                            error=str(ex),
                            exception_type=type(ex).__name__,
                            signal=e,
                        )

                    if isinstance(resp, dict) and resp.get("ok") is True:
                        positions[sym] = {
                            "qty": QTY,
                            "entry_price": e["entry_price"],
                            "flash_start_price": e["flash_start_price"],
                            "flash_drop_pct": e["flash_drop_pct"],
                            "pre_return_pct": e["pre_return_pct"],
                            "pre_slope_pct_per_hour": e["pre_slope_pct_per_hour"],
                            "target_price": e["target_price"],
                            "stop_price": e["stop_price"],
                            "recovery_fraction_at_entry": e.get("recovery_fraction_at_entry"),
                            "remaining_upside_pct": e.get("remaining_upside_pct"),
                            "actual_rebound_pct": e.get("actual_rebound_pct"),
                            "pending_created_at": e.get("pending_created_at"),
                            "confirmation_wait_seconds": e.get("confirmation_wait_seconds"),
                            "running_low_price": e.get("running_low_price"),
                            "signal_time": e.get("signal_time") or datetime.now(timezone.utc).isoformat(),
                            "submitted_at": datetime.now(timezone.utc).isoformat(),
                            "entry_timeout_seconds": ENTRY_TIMEOUT_SECONDS,
                            "state": "ENTRY_SUBMITTED",
                            "entry_order_id": resp.get("order_id"),
                            "entry_response": resp,
                            **_copy_volume_metrics(e),
                        }
                        save_positions(positions)
                    else:
                        print(f"NOT_TRACKING_POSITION {sym}: entry order failed/not accepted: {resp}", flush=True)
                        append_bot_event(
                            "ENTRY_NOT_TRACKED",
                            symbol=sym,
                            reason="entry_order_failed_or_not_accepted",
                            response=resp,
                            signal=e,
                        )
            else:
                print("TRIGGERS_FOUND=0", flush=True)

                def log_diag(label, e, include_score=False):
                    score_part = f"score={e.get('miss_score', 999):.2f} | " if include_score else ""
                    print(
                        f"{label} | {e['symbol']} | "
                        f"{score_part}"
                        f"drop={e.get('flash_drop_pct', 0):.2f}/{FLASH_DROP_PCT:.2f}% | "
                        f"pre_ret={e.get('pre_return_pct', 0):.2f}/{MIN_PRE_CRASH_RETURN_PCT:.2f}% | "
                        f"pre_slope={e.get('pre_slope_pct_per_hour', 0):.2f}/{MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR:.2f}%/hr | "
                        f"fails={e.get('failed', 'unknown')} | "
                        f"price={e.get('price', 0):.2f}",
                        flush=True
                    )

                if near_events:
                    top_drop = max(near_events, key=lambda e: e.get("flash_drop_pct", 0))
                    top_pre_ret = max(near_events, key=lambda e: e.get("pre_return_pct", 0))
                    top_pre_slope = max(near_events, key=lambda e: e.get("pre_slope_pct_per_hour", 0))
                    best_composite = min(near_events, key=lambda e: e.get("miss_score", 999))

                    log_diag("TOP_DROP", top_drop)
                    log_diag("TOP_PRE_RET", top_pre_ret)
                    log_diag("TOP_PRE_SLOPE", top_pre_slope)
                    log_diag("BEST_COMPOSITE", best_composite, include_score=True)
                else:
                    print("NO_DIAGNOSTIC_CANDIDATES", flush=True)

                # Rank all near misses globally across the full symbol universe.
                # Lower miss_score means closer to satisfying all trigger conditions.
                near_events.sort(
                    key=lambda e: float(e.get("miss_score", 999))
                )

                # Threshold candidates were already logged above, independently of
                # whether this scan also produced full signals.
                write_bot_output(status="no_trigger", triggers=[], nearest=[e for e in near_events if 0.0 < float(e.get("miss_score", 999)) <= NEAR_MISS_SCORE_CUTOFF][:25])

        except Exception as e:
            print("runner error:", type(e).__name__, e, flush=True)

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
