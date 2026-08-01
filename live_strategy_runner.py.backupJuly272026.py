import os, glob, time, json, math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from schwab_clients import SchwabTradeClient
from bot_output import write_bot_output, append_bot_event

TAPE_DIR = "/data/tapes"
STATE_FILE = "/data/positions.json"
TRIGGER_OUTCOMES_FILE = "/data/trigger_trade_outcomes.jsonl"

PRE_CRASH_TREND_MINUTES = 30
FLASH_WINDOW_MINUTES = 3
MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR = 0.50
MIN_PRE_CRASH_RETURN_PCT = 0.25
FLASH_DROP_PCT = 1.0
MAX_FLASH_DROP_PCT = 12.0

RECOVERY_TARGET_FRACTION = 0.60
STOP_LOSS_FRACTION_BELOW_ENTRY = 0.05

ENTRY_CUTOFF_HOUR_ET = 15
ENTRY_CUTOFF_MINUTE_ET = 30


QTY = 1
BUY_LIMIT_BUFFER_PCT = 0.002
REBOUND_CONFIRMATION_PCT = 0.001  # Strategy A: 0.10% rebound
STRATEGY_B_REBOUND_CONFIRMATION_PCT = 0.002  # Strategy B: 0.20% rebound
STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY = 0.02
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
STRATEGY_CONFIGS = {
    STRATEGY_A: {
        "rebound_confirmation_pct": REBOUND_CONFIRMATION_PCT,
        "stop_loss_fraction": STOP_LOSS_FRACTION_BELOW_ENTRY,
        "live_order_placement": True,
    },
    STRATEGY_B: {
        "rebound_confirmation_pct": STRATEGY_B_REBOUND_CONFIRMATION_PCT,
        "stop_loss_fraction": STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY,
        "live_order_placement": False,
    },
}

def append_strategy_event(strategy_id, event_type, **payload):
    append_bot_event(event_type, strategy_id=strategy_id, **payload)

def append_ab_paper_event(event_type, **payload):
    """Use only for genuinely identical research events such as near misses."""
    for strategy_id in (STRATEGY_A, STRATEGY_B):
        append_strategy_event(strategy_id, event_type, **payload)


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

        return {
            "volume_data_status_flash": "OK",
            "flash_volume_1m": flash_1m,
            "flash_volume_3m": flash_3m,
            "avg_volume_1m_pre30": avg_pre30,
            "flash_volume_ratio": ratio,
            "flash_dollar_volume_1m": flash_dollar_1m,
            "flash_dollar_volume_3m": flash_dollar_3m,
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

CACHE_MINUTES = 50
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

def detect_latest_flash(sym, g):
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
    pass_flash = FLASH_DROP_PCT <= flash_drop_pct <= MAX_FLASH_DROP_PCT

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
    if original_drop <= 0:
        return False, "invalid_original_drop"
    if target <= entry:
        return False, "target_reached_before_entry"
    if remaining < MIN_REMAINING_UPSIDE_PCT:
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

def main():
    print("🚀 V14 FLASH-DIP RUNNER ONLINE — STRATEGY A LIVE + STRATEGY B PAPER SHADOW", flush=True)
    print(f"PRE={PRE_CRASH_TREND_MINUTES}m FLASH={FLASH_WINDOW_MINUTES}m DROP={FLASH_DROP_PCT}-{MAX_FLASH_DROP_PCT}% TARGET={RECOVERY_TARGET_FRACTION} STOP={STOP_LOSS_FRACTION_BELOW_ENTRY}", flush=True)

    trader = make_trader()
    last_trading_token_touch = 0
    last_market_token_touch = 0
    positions = load_positions()
    print(f"LOADED_POSITIONS={list(positions.keys())}", flush=True)

    # In-memory research tracker for NEAR_MISS forward returns.
    near_miss_tracker = {}

    # Symbols that met the full signal but are waiting for a 0.10% rebound
    # from the lowest live price observed after qualification.
    pending_entries = {STRATEGY_A: {}, STRATEGY_B: {}}

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

            df = read_data()
            if df is None or df.empty:
                print("No tape yet.", flush=True)
                time.sleep(POLL_SECONDS)
                continue

            prices_now = latest_prices(df)
            manage_exits(trader, positions, prices_now)

            now_utc = datetime.now(timezone.utc)

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
                        append_ab_paper_event(
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
                had_pending = False
                for strategy_id, cfg in STRATEGY_CONFIGS.items():
                    pending = pending_entries[strategy_id].get(sym)
                    if pending is None:
                        continue
                    had_pending = True
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

                if had_pending:
                    continue

                event = detect_latest_flash(sym, g)

                if event:
                    if not current_price or current_price <= 0:
                        continue

                    current_price = float(current_price)
                    event.update(fetch_flash_volume_metrics(sym))
                    for strategy_id, cfg in STRATEGY_CONFIGS.items():
                        strategy_event = dict(event)
                        strategy_event["strategy_id"] = strategy_id
                        strategy_event["stop_price"] = current_price * (1 - cfg["stop_loss_fraction"])
                        pending_entries[strategy_id][sym] = {
                            "created_at": now_utc,
                            "lowest_price": current_price,
                            "initial_signal": strategy_event,
                        }
                        append_strategy_event(strategy_id, "PENDING_REBOUND_CREATED",
                            symbol=sym, current_price=current_price,
                            required_rebound_pct=cfg["rebound_confirmation_pct"] * 100,
                            timeout_seconds=PENDING_REBOUND_TIMEOUT_SECONDS, signal=strategy_event)
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
                            "FLASH_DROP_PCT": FLASH_DROP_PCT,
                            "MAX_FLASH_DROP_PCT": MAX_FLASH_DROP_PCT,
                            "MIN_PRE_CRASH_RETURN_PCT": MIN_PRE_CRASH_RETURN_PCT,
                            "MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR": MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR,
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

                # Research ledger: persist top nearest misses so we can later
                # calculate forward returns and tune thresholds from real data.
                for e in near_events[:5]:
                    append_ab_paper_event(
                        "NEAR_MISS",
                        symbol=e.get("symbol"),
                        candidate=e,
                        thresholds={
                            "FLASH_DROP_PCT": FLASH_DROP_PCT,
                            "MAX_FLASH_DROP_PCT": MAX_FLASH_DROP_PCT,
                            "MIN_PRE_CRASH_RETURN_PCT": MIN_PRE_CRASH_RETURN_PCT,
                            "MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR": MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR,
                        },
                    )

                    key = f"{e.get('symbol')}|{now_utc.isoformat()}"
                    near_miss_tracker[key] = {
                        "timestamp": now_utc,
                        "symbol": e.get("symbol"),
                        "entry_price": float(e.get("price", 0) or 0),
                        "candidate": dict(e),
                    }

                write_bot_output(status="no_trigger", triggers=[], nearest=near_events[:5])

        except Exception as e:
            print("runner error:", type(e).__name__, e, flush=True)

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
