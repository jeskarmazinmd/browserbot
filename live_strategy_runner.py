import os, glob, time, json, math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from schwab_clients import SchwabTradeClient
from bot_output import write_bot_output, append_bot_event
from quote_source import LiveQuoteSource
from types import SimpleNamespace
from engine.events import MarketSnapshot, Quote, SignalEvent
from strategies.generic_registry import evaluate_all as evaluate_generic_strategies
from strategies.derived_runtime import DERIVED_STRATEGY_IDS, derive_signals
from strategies.flash_nearest_miss import score as score_flash_window
from strategies.registry import (
    DERIVED_RUNTIME_STRATEGY_IDS,
    MINUTE_STRATEGIES,
    REPORTING_STRATEGY_MODULES,
    flash_accepts,
    flash_strategy_configs,
    on_minute_snapshot as run_minute_strategies,
    refresh_flash_entry,
    validate_flash_entry,
)
from regime_logger import log_regime, latest_regime
from paper_outcome_tracker import PaperOutcomeTracker
from strategy_diagnostics import diagnostics

RUN_MODE = os.environ.get("RUN_MODE", "LIVE")
REPLAY_TAPE_PATH = os.environ.get("REPLAY_TAPE_PATH")
RUN_ID = os.environ.get("RUN_ID", "live")

if RUN_MODE == "REPLAY":
    DATA_ROOT = Path("./replay") / RUN_ID
else:
    DATA_ROOT = Path("/data")

DATA_ROOT.mkdir(parents=True, exist_ok=True)

TAPE_DIR = str(DATA_ROOT / "tapes")
STATE_FILE = str(DATA_ROOT / "positions.json")
TRIGGER_OUTCOMES_FILE = str(DATA_ROOT / "trigger_trade_outcomes.jsonl")

PRE_CRASH_TREND_MINUTES = 30
FLASH_WINDOW_MINUTES = 3
MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR = 0.50
MIN_PRE_CRASH_RETURN_PCT = 0.25
FLASH_DROP_PCT = 1.0
# Strategy H aliases retained for reporting/near-miss code. Rules live in strategy_h.py.
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

STRATEGY_CONFIGS = flash_strategy_configs()

STRATEGY_A = "A"
STRATEGY_B = "B"
STRATEGY_D = "D"
STRATEGY_H = "H"

# Reporting and near-miss aliases derived from module-owned Strategy H rules.
STRATEGY_H_MIN_FLASH_DROP_PCT = STRATEGY_CONFIGS[STRATEGY_H]["flash_drop_pct"]
STRATEGY_H_MAX_FLASH_DROP_PCT = STRATEGY_CONFIGS[STRATEGY_H]["max_flash_drop_pct"]
STRATEGY_H_MIN_PRE_R2 = STRATEGY_CONFIGS[STRATEGY_H]["min_pre_r2"]
STRATEGY_H_MAX_PRE_SLOPE_PCT_PER_HOUR = (
    STRATEGY_CONFIGS[STRATEGY_H]["max_pre_slope_pct_per_hour"]
)

# Independent strategy orchestration settings. Individual strategy rules and
# thresholds live exclusively in strategies/strategy_*.py.
INDEPENDENT_FORWARD_START_UTC = "2026-07-31T13:30:00+00:00"
INDEPENDENT_COOLDOWN_MINUTES = 30
INDEPENDENT_MIN_PRICE = 1.00
INDEPENDENT_MAX_PRICE = 1000.00
UNIVERSE_MANIFEST_DIR = DATA_ROOT

_UNIVERSE_MANIFEST_CACHE = {"path": None, "mtime_ns": None, "symbols": {}}

def append_strategy_event(strategy_id, event_type, **payload):
    append_bot_event(event_type, strategy_id=strategy_id, **payload)

def append_ab_paper_event(event_type, **payload):
    """Use only for genuinely identical research events such as near misses."""
    for strategy_id in (STRATEGY_A, STRATEGY_B):
        append_strategy_event(strategy_id, event_type, **payload)


def strategy_accepts_flash(strategy_id, event):
    """Delegate flash admission to the registered strategy module."""
    return flash_accepts(strategy_id, event, MAX_FLASH_DROP_PCT)


def is_regular_market_hours_et():
    if RUN_MODE == "REPLAY":
        now = quote_source.now().astimezone(ZoneInfo("America/New_York"))
    else:
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


def _confirm_recent_volume_ratio(symbol, lookback_minutes=30):
    """Fetch volume only after an EMA1 price crossover exists."""
    try:
        candles = _minute_candles(
            symbol,
            lookback_minutes=max(lookback_minutes, 40),
        )

        if len(candles) < 12:
            return None

        completed = (
            candles.iloc[:-1]
            if len(candles) > 1
            else candles
        )
        latest_volume = float(completed.iloc[-1]["volume"])
        baseline = completed.iloc[-11:-1]["volume"].astype(float)
        average_volume = float(baseline.mean())

        if average_volume <= 0:
            return None

        return latest_volume / average_volume

    except Exception:
        return None


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
    """Use the replay clock in replay mode and wall time in live mode."""
    if RUN_MODE == "REPLAY":
        now_et = quote_source.now().astimezone(
            ZoneInfo("America/New_York")
        )
    else:
        now_et = datetime.now(timezone.utc).astimezone(
            ZoneInfo("America/New_York")
        )

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



if RUN_MODE == "REPLAY":
    from replay_quote_source import ReplayQuoteSource

    if not REPLAY_TAPE_PATH:
        raise RuntimeError("REPLAY_TAPE_PATH required in REPLAY mode")

    quote_source = ReplayQuoteSource(REPLAY_TAPE_PATH)
else:
    # Use quote_source.py's incremental reader so its compact persistent
    # minute cache survives process and machine restarts.  Passing the legacy
    # local reader here bypasses that persistence layer.
    quote_source = LiveQuoteSource()


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

def measure_latest_flash(sym, g, prices=None):
    """Return flash-window measurements once the complete, current window exists."""
    if prices is None:
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

    return {
        "symbol": sym,
        "entry_price": flash_end,
        "flash_start_price": flash_start,
        "flash_drop_pct": flash_drop_pct,
        "pre_return_pct": pre_return_pct,
        "pre_slope_pct_per_hour": pre_slope_pct_per_hour,
        "pre_r2": pre_r2,
        "price": flash_end,
        "signal_window_end": window.index[-1].isoformat(),
    }


def detect_latest_flash(sym, g, min_flash_drop_pct=FLASH_DROP_PCT, measurement=None):
    measured = measurement if measurement is not None else measure_latest_flash(sym, g)
    if measured is None:
        return None

    pre_return_pct = float(measured["pre_return_pct"])
    pre_slope_pct_per_hour = float(measured["pre_slope_pct_per_hour"])
    flash_drop_pct = float(measured["flash_drop_pct"])

    pass_pre_return = pre_return_pct >= MIN_PRE_CRASH_RETURN_PCT
    pass_pre_slope = not math.isnan(pre_slope_pct_per_hour) and pre_slope_pct_per_hour >= MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR
    pass_flash = min_flash_drop_pct <= flash_drop_pct <= MAX_FLASH_DROP_PCT

    if not (pass_pre_return and pass_pre_slope and pass_flash):
        return None

    entry = float(measured["entry_price"])
    flash_start = float(measured["flash_start_price"])
    target = entry + RECOVERY_TARGET_FRACTION * (flash_start - entry)
    stop = entry * (1 - STOP_LOSS_FRACTION_BELOW_ENTRY)

    return {
        **measured,
        "target_price": target,
        "stop_price": stop,
    }


def score_flash_near_miss(strategy_id, measurement):
    """Score a complete flash window against one strategy's pre-entry rules."""
    return score_flash_window(
        measurement,
        strategy_id,
        STRATEGY_CONFIGS[strategy_id],
        MIN_PRE_CRASH_RETURN_PCT,
        MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR,
        MAX_FLASH_DROP_PCT,
    )

def refresh_event_for_entry(event, current_price, strategy_id):
    """Delegate confirmed-entry construction to the strategy module."""
    return refresh_flash_entry(strategy_id, event, current_price)


def validate_confirmed_entry(event):
    """Delegate confirmed-entry validation to the strategy module."""
    strategy_id = str(event.get("strategy_id") or STRATEGY_A)
    return validate_flash_entry(strategy_id, event, MIN_REMAINING_UPSIDE_PCT)


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
                            pos["entry_fill_regime"] = latest_regime()
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
                pos["entry_fill_regime"] = latest_regime()
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
            "legacy_eligible": bool(meta.get("legacy_eligible", False)),
        }
    except Exception:
        return {"primary_universe": "UNKNOWN", "universe_memberships": [], "sampling_tier": "UNKNOWN", "dynamic_promoted": False}


def completed_minute_snapshots(df, after_timestamp=None):
    """Build complete one-minute snapshots from the rolling minute cache.

    The newest clock minute is withheld because the collector may still be
    appending symbols for that minute. Once a newer minute appears, the prior
    minute is complete and safe to dispatch.
    """
    if df is None or df.empty:
        return []

    required = {"timestamp", "symbol", "price"}
    if not required.issubset(df.columns):
        return []

    work = df.dropna(
        subset=["timestamp", "symbol", "price"],
    ).copy()

    if work.empty:
        return []

    work["timestamp"] = pd.to_datetime(
        work["timestamp"],
        utc=True,
        errors="coerce",
    )
    work["price"] = pd.to_numeric(
        work["price"],
        errors="coerce",
    )
    work = work.dropna(
        subset=["timestamp", "symbol", "price"],
    )

    if work.empty:
        return []

    newest_minute = work["timestamp"].max().floor("min")
    completed_through = newest_minute - pd.Timedelta(minutes=1)

    eligible = work[
        work["timestamp"] <= completed_through
    ]

    if after_timestamp is not None:
        after = pd.Timestamp(after_timestamp)

        if after.tzinfo is None:
            after = after.tz_localize("UTC")
        else:
            after = after.tz_convert("UTC")

        eligible = eligible[
            eligible["timestamp"] > after
        ]

    if eligible.empty:
        return []

    expected_symbol_count = int(
        work["symbol"].astype(str).nunique()
    )
    snapshots = []

    for timestamp, minute_rows in eligible.groupby(
        "timestamp",
        sort=True,
    ):
        latest = (
            minute_rows
            .sort_values("timestamp")
            .drop_duplicates(
                subset=["symbol"],
                keep="last",
            )
        )

        quotes = {
            str(row["symbol"]): Quote(
                price=float(row["price"]),
                total_volume=None,
                bid=None,
                ask=None,
            )
            for _, row in latest.iterrows()
        }

        snapshots.append(
            MarketSnapshot(
                timestamp=pd.Timestamp(timestamp).to_pydatetime(),
                quotes=quotes,
                expected_symbol_count=expected_symbol_count,
                returned_symbol_count=len(quotes),
                fetch_duration_seconds=0.0,
                metadata={
                    "source": "completed_minute_cache",
                    "cadence": "minute",
                },
            )
        )

    return snapshots


def snapshot_signal_payload(signal):
    """Convert SignalEvent to the established paper-event payload schema."""
    timestamp = pd.Timestamp(signal.timestamp)

    payload = {
        "strategy_id": str(signal.strategy_id),
        "symbol": str(signal.symbol),
        "timestamp": timestamp.isoformat(),
        "setup_id": (
            f"{signal.strategy_id}|{signal.symbol}|"
            f"{timestamp.floor('min').isoformat()}"
        ),
        **_universe_metadata(signal.symbol, signal.timestamp),
        **dict(signal.data or {}),
    }

    payload.setdefault("live_order_placement", False)

    return payload


def main():
    print("🚀 CADENCE-AWARE STRATEGY RUNNER ONLINE", flush=True)
    print(f"PRE={PRE_CRASH_TREND_MINUTES}m FLASH={FLASH_WINDOW_MINUTES}m DROP={FLASH_DROP_PCT}-{MAX_FLASH_DROP_PCT}% TARGET={RECOVERY_TARGET_FRACTION} STOP={STOP_LOSS_FRACTION_BELOW_ENTRY}", flush=True)

    trader = make_trader() if RUN_MODE == "LIVE" else None
    last_trading_token_touch = 0
    last_market_token_touch = 0
    positions = load_positions()
    print(f"LOADED_POSITIONS={list(positions.keys())}", flush=True)
    paper_outcomes = PaperOutcomeTracker(
        DATA_ROOT,
        eod_hour=EOD_EXIT_HOUR_ET,
        eod_minute=EOD_EXIT_MINUTE_ET,
    )
    print(
        "PAPER_OUTCOME_TRACKER_ONLINE "
        f"active={len(paper_outcomes.active)} seen={len(paper_outcomes.seen)}",
        flush=True,
    )
    print(
        "DERIVED_STRATEGIES_ONLINE " + ",".join(sorted(DERIVED_STRATEGY_IDS)),
        flush=True,
    )
    for strategy in MINUTE_STRATEGIES:
        strategy_id = str(getattr(strategy, "name", type(strategy).__name__))
        diagnostics.define(
            strategy_id,
            "RUNNING",
            runtime_path="minute",
            nearest_miss_status="no rejected candidate with sufficient history yet",
        )
    for strategy_id in STRATEGY_CONFIGS:
        diagnostics.define(strategy_id, "RUNNING", runtime_path="flash")
    derived_parents = {
        **{key: "B" for key in ("C1", "C2", "C3", "C4", "G", "J1", "J2", "J3", "J4", "J5", "J6")},
        "E": "A", "I": "A", "F": "D",
        **{key: "A" for key in ("K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9", "L", "M", "N", "O", "P", "Q", "R", "S")},
    }
    for strategy_id, parent_id in derived_parents.items():
        diagnostics.define(
            strategy_id,
            "WAITING_PARENT",
            runtime_path="derived",
            parent_strategy=parent_id,
        )
    inactive_ids = set(REPORTING_STRATEGY_MODULES) - set(DERIVED_RUNTIME_STRATEGY_IDS)
    for strategy_id in inactive_ids:
        diagnostics.define(
            strategy_id,
            "INACTIVE",
            runtime_path="legacy_reporting_only",
            reason="not connected to runtime evaluation",
        )
    parent_signal_counts = {"A": 0, "B": 0, "D": 0}
    derived_signal_counts = {key: 0 for key in derived_parents}
    diagnostics.flush(force=True)

    # In-memory research tracker for NEAR_MISS forward returns.
    near_miss_tracker = {}
    near_miss_logged = set()  # (market_day, strategy_id, symbol)
    near_miss_logged_day = None

    # Symbols that met the full signal but are waiting for a 0.10% rebound
    # from the lowest live price observed after qualification.
    pending_entries = {
        strategy_id: {}
        for strategy_id in STRATEGY_CONFIGS
    }
    last_flash_signature = {
        strategy_id: {}
        for strategy_id in STRATEGY_CONFIGS
    }

    # Native independent-strategy signals are deduplicated by emitted minute and
    # also receive a per-symbol cooldown to avoid repeatedly entering one trend.
    independent_last_signal = {}
    independent_dedupe_day = None

    # Completed-minute strategies warm from the existing cache once, then
    # receive each newly completed minute exactly once.
    last_minute_snapshot_timestamp = None

    while True:
        try:
            now_ts = time.time()

            if RUN_MODE == "LIVE":
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

            if RUN_MODE == "REPLAY":
                print(
                    f"REPLAY_CLOCK {quote_source.now()} rows={len(df)}",
                    flush=True,
                )

            if df is None or df.empty:
                print("No tape yet.", flush=True)
                time.sleep(0 if RUN_MODE == "REPLAY" else POLL_SECONDS)
                continue

            current_regime = log_regime(df)

            prices_now = latest_prices(df)
            if RUN_MODE == "LIVE":
                manage_exits(trader, positions, prices_now)

            now_utc = quote_source.now()
            for outcome in paper_outcomes.update(prices_now, now_utc):
                print(
                    "PAPER_OUTCOME "
                    f"strategy={outcome['strategy_id']} symbol={outcome['symbol']} "
                    f"reason={outcome['exit_reason']} pnl={outcome['pnl']:+.2f}",
                    flush=True,
                )
            market_day = now_utc.astimezone(ZoneInfo("America/New_York")).date().isoformat()
            if market_day != near_miss_logged_day:
                near_miss_logged.clear()
                near_miss_logged_day = market_day

            # Do not generate, record, or paper-track signals/near misses
            # outside regular trading hours. Broker-side exits remain active,
            # and manage_exits() above still handles the 15:55 ET flattening.
            if not is_regular_market_hours_et():
                write_bot_output(status="outside_rth", triggers=[], nearest=[])

                if RUN_MODE == "REPLAY" and quote_source.finished:
                    print(
                        f"REPLAY_COMPLETE clock={quote_source.now()}",
                        flush=True,
                    )
                    break

                time.sleep(0 if RUN_MODE == "REPLAY" else POLL_SECONDS)
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
            spy_5m_return_pct = None
            spy_1m_return_pct = None
            market_confirmation_symbol = None
            try:
                spy_group = df[df["symbol"].astype(str) == "SPY"].sort_values("timestamp")
                if len(spy_group) >= 31:
                    spy_prices = spy_group["price"].astype(float).tail(31)
                    spy_30m_return_pct = _simple_return_pct(spy_prices.iloc[0], spy_prices.iloc[-1])
                spy_minutes = minute_prices(spy_group).dropna()
                if len(spy_minutes) >= 6:
                    spy_5m_return_pct = _simple_return_pct(spy_minutes.iloc[-6], spy_minutes.iloc[-1])
                if len(spy_minutes) >= 2:
                    spy_1m_return_pct = _simple_return_pct(spy_minutes.iloc[-2], spy_minutes.iloc[-1])
                market_confirmation_symbol = "SPY"
                qqq_group = df[df["symbol"].astype(str) == "QQQ"].sort_values("timestamp")
                qqq_minutes = minute_prices(qqq_group).dropna()
                if len(qqq_minutes) >= 6:
                    qqq_5m = _simple_return_pct(qqq_minutes.iloc[-6], qqq_minutes.iloc[-1])
                    qqq_1m = _simple_return_pct(qqq_minutes.iloc[-2], qqq_minutes.iloc[-1]) if len(qqq_minutes) >= 2 else None
                    if spy_5m_return_pct is None or qqq_5m > spy_5m_return_pct:
                        spy_5m_return_pct = qqq_5m
                        spy_1m_return_pct = qqq_1m
                        market_confirmation_symbol = "QQQ"
            except Exception:
                spy_30m_return_pct = None
                spy_5m_return_pct = None
                spy_1m_return_pct = None

            scan_stats = {
                "symbols_seen": 0,
                "positions_skipped": 0,
                "triggers": 0,
                "empty_minute_series": 0,
                "insufficient_history": 0,
                "missing_minutes": 0,
                "stale_windows": 0,
                "invalid_prices": 0,
                "calculation_errors": 0,
                "near_candidates": 0,
            }
            scan_error_samples = []

            minute_snapshots = completed_minute_snapshots(
                df,
                after_timestamp=last_minute_snapshot_timestamp,
            )
            warming_minute_pipeline = (
                last_minute_snapshot_timestamp is None
            )

            for minute_snapshot in minute_snapshots:
                dispatch_snapshot = minute_snapshot

                if (
                    not warming_minute_pipeline
                    and RUN_MODE == "LIVE"
                ):
                    dispatch_snapshot = MarketSnapshot(
                        timestamp=minute_snapshot.timestamp,
                        quotes=minute_snapshot.quotes,
                        expected_symbol_count=(
                            minute_snapshot.expected_symbol_count
                        ),
                        returned_symbol_count=(
                            minute_snapshot.returned_symbol_count
                        ),
                        fetch_duration_seconds=(
                            minute_snapshot.fetch_duration_seconds
                        ),
                        metadata={
                            **minute_snapshot.metadata,
                            "confirm_recent_volume_ratio": (
                                _confirm_recent_volume_ratio
                            ),
                        },
                    )

                minute_signals, minute_errors = run_minute_strategies(
                    dispatch_snapshot
                )
                last_minute_snapshot_timestamp = (
                    minute_snapshot.timestamp
                )

                for strategy_id, exc in minute_errors:
                    scan_stats["calculation_errors"] += 1
                    print(
                        "MINUTE_STRATEGY_EVALUATION_ERROR "
                        f"{strategy_id}: {type(exc).__name__}: {exc}",
                        flush=True,
                    )
                    append_strategy_event(
                        strategy_id,
                        "STRATEGY_EVALUATION_ERROR",
                        error=f"{type(exc).__name__}: {exc}",
                        cadence="minute",
                    )

                if warming_minute_pipeline:
                    continue

                for signal in minute_signals:
                    independent = snapshot_signal_payload(signal)
                    strategy_id = independent["strategy_id"]
                    symbol = independent["symbol"]
                    entry_price = float(
                        independent.get("entry_price", 0.0) or 0.0
                    )

                    if symbol in positions:
                        continue

                    if not (
                        INDEPENDENT_MIN_PRICE
                        <= entry_price
                        <= INDEPENDENT_MAX_PRICE
                    ):
                        continue

                    emitted_ts = pd.Timestamp(
                        independent["timestamp"]
                    )
                    dedupe_key = (
                        market_day,
                        strategy_id,
                        symbol,
                    )
                    prior_ts = independent_last_signal.get(
                        dedupe_key
                    )

                    if prior_ts is not None:
                        age_minutes = (
                            emitted_ts - prior_ts
                        ).total_seconds() / 60.0

                        if (
                            age_minutes
                            < INDEPENDENT_COOLDOWN_MINUTES
                        ):
                            continue

                    independent_last_signal[dedupe_key] = emitted_ts
                    independent_events.append(independent)

                    append_strategy_event(
                        strategy_id,
                        "SIGNAL",
                        symbol=symbol,
                        signal=independent,
                        signal_regime=latest_regime(),
                        thresholds={
                            "INDEPENDENT_FORWARD_START_UTC": (
                                INDEPENDENT_FORWARD_START_UTC
                            ),
                            "INDEPENDENT_COOLDOWN_MINUTES": (
                                INDEPENDENT_COOLDOWN_MINUTES
                            ),
                            "LIVE_ORDER_PLACEMENT": False,
                            "CADENCE": "minute",
                        },
                    )
                    paper_outcomes.register(independent)

            if warming_minute_pipeline and minute_snapshots:
                print(
                    "MINUTE_STRATEGY_WARMUP "
                    f"snapshots={len(minute_snapshots)} "
                    f"through={last_minute_snapshot_timestamp}",
                    flush=True,
                )

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

                # Detect using the lowest configured threshold, then admit only the
                # strategies whose own flash threshold is satisfied.
                flash_prices = minute_prices(g)
                flash_measurement = measure_latest_flash(sym, g, prices=flash_prices)
                if flash_measurement is not None:
                    near_events.append(flash_measurement)
                    scan_stats["near_candidates"] += 1
                else:
                    needed = PRE_CRASH_TREND_MINUTES + FLASH_WINDOW_MINUTES + 1
                    if flash_prices.empty:
                        scan_stats["empty_minute_series"] += 1
                    elif len(flash_prices) < needed:
                        scan_stats["insufficient_history"] += 1
                    else:
                        diagnostic_window = flash_prices.iloc[-needed:]
                        if diagnostic_window.isna().any():
                            scan_stats["missing_minutes"] += 1
                        elif (diagnostic_window <= 0).any():
                            scan_stats["invalid_prices"] += 1
                        else:
                            latest = diagnostic_window.index[-1]
                            if latest.tzinfo is None:
                                latest = latest.tz_localize("UTC")
                            else:
                                latest = latest.tz_convert("UTC")
                            age = (pd.Timestamp.now(tz="UTC") - latest).total_seconds()
                            if age > MAX_QUOTE_AGE_SECONDS:
                                scan_stats["stale_windows"] += 1
                            else:
                                scan_stats["invalid_prices"] += 1

                event = detect_latest_flash(
                    sym,
                    g,
                    min(cfg["flash_drop_pct"] for cfg in STRATEGY_CONFIGS.values()),
                    measurement=flash_measurement,
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
                f"stale_windows={scan_stats['stale_windows']} "
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

            flash_nearest = {}

            def retain_nearest(strategy_id, candidate):
                current = flash_nearest.get(strategy_id)
                if current is None or float(candidate.get("miss_score", 999)) < float(current.get("miss_score", 999)):
                    flash_nearest[strategy_id] = dict(candidate)

            for measurement in near_events:
                for strategy_id in (STRATEGY_A, STRATEGY_B, STRATEGY_D, STRATEGY_H):
                    candidate = score_flash_near_miss(strategy_id, measurement)
                    if candidate is None:
                        continue
                    retain_nearest(strategy_id, candidate)
                    extra_thresholds = None
                    if strategy_id == STRATEGY_H:
                        extra_thresholds = {
                            "MIN_PRE_R2": STRATEGY_H_MIN_PRE_R2,
                            "MAX_PRE_CRASH_SLOPE_PCT_PER_HOUR": STRATEGY_H_MAX_PRE_SLOPE_PCT_PER_HOUR,
                        }
                    log_threshold_candidate(
                        strategy_id,
                        candidate,
                        STRATEGY_CONFIGS[strategy_id]["flash_drop_pct"],
                        extra_thresholds=extra_thresholds,
                    )

            for strategy_id, signal_rows in (
                (STRATEGY_A, events_a),
                (STRATEGY_B, events_b),
                (STRATEGY_D, events_d),
                (STRATEGY_H, events_h),
            ):
                diagnostics.evaluated(
                    strategy_id,
                    now_utc.isoformat(),
                    scan_stats["symbols_seen"],
                    signal_count=len(signal_rows),
                    nearest_miss=flash_nearest.get(strategy_id),
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
                    try:
                        e.update(_universe_metadata(
                            e.get("symbol"),
                            e.get("timestamp")
                        ))
                    except Exception:
                        pass
                    e["market_5m_return_pct"] = spy_5m_return_pct
                    e["market_1m_return_pct"] = spy_1m_return_pct
                    e["market_confirmation_symbol"] = market_confirmation_symbol

                    append_strategy_event(
                        e.get("strategy_id", STRATEGY_A),
                        "SIGNAL",
                        symbol=e.get("symbol"),
                        signal=e,
                        signal_regime=latest_regime(),
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
                    paper_outcomes.register(e)
                    if e.get("strategy_id") in parent_signal_counts:
                        parent_signal_counts[e["strategy_id"]] += 1
                    for derived in derive_signals(e):
                        append_strategy_event(
                            derived["strategy_id"],
                            "SIGNAL",
                            symbol=derived["symbol"],
                            signal=derived,
                            signal_regime=latest_regime(),
                            thresholds={
                                "DERIVED_FROM": derived["source_strategy_id"],
                                "LIVE_ORDER_PLACEMENT": False,
                                "EXIT_MODEL": derived["exit_model"],
                            },
                        )
                        paper_outcomes.register(derived)
                        derived_signal_counts[derived["strategy_id"]] += 1

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
                        if RUN_MODE == "LIVE":
                            resp = trader.place_entry_trigger_oco_order(
                                sym,
                                qty=QTY,
                                buy_limit_price=buy_limit_price,
                                target_price=e["target_price"],
                                stop_price=e["stop_price"],
                            )
                        else:
                            resp = {
                                "ok": True,
                                "replay": True,
                                "order_id": None,
                                "message": "Replay mode - simulated entry",
                            }
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
                            "order_submission_regime": latest_regime(),
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

            for strategy_id, parent_id in derived_parents.items():
                diagnostics.parent_state(
                    strategy_id,
                    parent_id,
                    parent_signal_counts[parent_id],
                    derived_signal_counts[strategy_id],
                )
            diagnostics.flush()

        except Exception as e:
            print("runner error:", type(e).__name__, e, flush=True)

        if RUN_MODE == "REPLAY" and quote_source.finished:
            print(
                f"REPLAY_COMPLETE clock={quote_source.now()}",
                flush=True,
            )
            break

        time.sleep(0 if RUN_MODE == "REPLAY" else POLL_SECONDS)

if __name__ == "__main__":
    main()
