import os, glob, time, json, math
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from schwab_clients import SchwabTradeClient
from bot_output import write_bot_output, append_bot_event

TAPE_DIR = "/data/tapes"
STATE_FILE = "/data/positions.json"

PRE_CRASH_TREND_MINUTES = 30
FLASH_WINDOW_MINUTES = 3
MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR = 0.50
MIN_PRE_CRASH_RETURN_PCT = 0.25
FLASH_DROP_PCT = 2.0
MAX_FLASH_DROP_PCT = 12.0

RECOVERY_TARGET_FRACTION = 0.60
STOP_LOSS_FRACTION_BELOW_ENTRY = 0.05

ENTRY_CUTOFF_HOUR_ET = 15
ENTRY_CUTOFF_MINUTE_ET = 30


QTY = 1
BUY_LIMIT_BUFFER_PCT = 0.002

# Forced exit before regular market close.
# 15:55 ET = 12:55 PT.
EOD_EXIT_HOUR_ET = 15
EOD_EXIT_MINUTE_ET = 55
MAX_ORDER_ATTEMPTS_PER_BOOT = 10
POLL_SECONDS = 5
MAX_QUOTE_AGE_SECONDS = 300

attempted = set()


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

def read_data():
    # Read only the recent quote tape tail.
    # Prevents the strategy runner from loading the entire growing intraday CSV into RAM.
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    candidates = [
        Path("/data/tapes") / f"quotes_{today}.csv",
        Path(f"quotes_{today}.csv"),
    ]

    tape = next((x for x in candidates if x.exists() and x.stat().st_size > 0), None)
    if tape is None:
        return None

    import subprocess
    import tempfile

    # Enough rows for ~30m pre-window + 3m flash window across ~684 symbols,
    # while avoiding huge memory spikes.
    max_rows = 500_000

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            subprocess.run(
                ["tail", "-n", str(max_rows), str(tape)],
                stdout=tmp,
                stderr=subprocess.DEVNULL,
                check=True,
            )
    except Exception as e:
        print(f"read_data tail error: {type(e).__name__}: {e}", flush=True)
        return None

    try:
        if tmp_path is None or tmp_path.stat().st_size == 0:
            return None

        # Parse the temporary file directly.  This avoids retaining both a
        # large Python string and a StringIO copy alongside the DataFrame.
        df = pd.read_csv(
            tmp_path,
            names=["timestamp", "symbol", "price"],
            dtype={"symbol": "string"},
            low_memory=False,
        )
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    df = df[df["timestamp"] != "timestamp_utc"]
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", errors="coerce", utc=True)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["timestamp", "symbol", "price"])
    return df

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
    """Convert irregular raw quotes into one price observation per minute."""
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

    # Use the final quote observed in each clock minute.
    # Do not fill missing minutes: a gap should not be mistaken for
    # continuously observed market data.
    return (
        data
        .set_index("timestamp")["price"]
        .resample("1min")
        .last()
        .dropna()
    )

def detect_latest_flash(sym, g):
    prices = minute_prices(g)

    needed = PRE_CRASH_TREND_MINUTES + FLASH_WINDOW_MINUTES + 1
    if len(prices) < needed:
        return None

    flash = prices.iloc[-(FLASH_WINDOW_MINUTES + 1):]
    pre = prices.iloc[
        -(PRE_CRASH_TREND_MINUTES + FLASH_WINDOW_MINUTES + 1):
        -FLASH_WINDOW_MINUTES
    ]

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
                        # Entry is accepted but has not filled.
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

        # Schwab confirms that a real position exists.
        pos["state"] = "FILLED"

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
    print("🚀 V14 FLASH-DIP RUNNER ONLINE — EXACT LOGIC", flush=True)
    print(f"PRE={PRE_CRASH_TREND_MINUTES}m FLASH={FLASH_WINDOW_MINUTES}m DROP={FLASH_DROP_PCT}-{MAX_FLASH_DROP_PCT}% TARGET={RECOVERY_TARGET_FRACTION} STOP={STOP_LOSS_FRACTION_BELOW_ENTRY}", flush=True)

    trader = make_trader()
    last_trading_token_touch = 0
    last_market_token_touch = 0
    positions = load_positions()
    print(f"LOADED_POSITIONS={list(positions.keys())}", flush=True)

    # In-memory research tracker for NEAR_MISS forward returns.
    near_miss_tracker = {}

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
                        append_bot_event(
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

            for sym, g in df.groupby("symbol"):
                if sym in positions:
                    continue

                event = detect_latest_flash(sym, g)

                if event:
                    events.append(event)
                else:
                    try:
                        prices = minute_prices(g)

                        needed = PRE_CRASH_TREND_MINUTES + FLASH_WINDOW_MINUTES + 1
                        if len(prices) >= needed:

                            flash = prices.iloc[-(FLASH_WINDOW_MINUTES + 1):]
                            flash_start = float(flash.iloc[0])
                            flash_end = float(flash.iloc[-1])

                            pre = prices.iloc[
        -(PRE_CRASH_TREND_MINUTES + FLASH_WINDOW_MINUTES + 1):
        -FLASH_WINDOW_MINUTES
    ]
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
                    except Exception:
                        pass

            events.sort(key=lambda e: e["flash_drop_pct"], reverse=True)

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

                write_bot_output(status="trigger", triggers=events[:10], nearest=[])

                # Strict full-detail ledger: record every threshold-passing signal,
                # independent of whether we later attempt an order.
                for e in events:
                    append_bot_event(
                        "SIGNAL",
                        symbol=e.get("symbol"),
                        signal=e,
                        thresholds={
                            "FLASH_DROP_PCT": FLASH_DROP_PCT,
                            "MAX_FLASH_DROP_PCT": MAX_FLASH_DROP_PCT,
                            "MIN_PRE_CRASH_RETURN_PCT": MIN_PRE_CRASH_RETURN_PCT,
                            "MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR": MIN_PRE_CRASH_SLOPE_PCT_PER_HOUR,
                            "RECOVERY_TARGET_FRACTION": RECOVERY_TARGET_FRACTION,
                            "STOP_LOSS_FRACTION_BELOW_ENTRY": STOP_LOSS_FRACTION_BELOW_ENTRY,
                            "EOD_EXIT_HOUR_ET": EOD_EXIT_HOUR_ET,
                            "EOD_EXIT_MINUTE_ET": EOD_EXIT_MINUTE_ET,
                            "QTY": QTY,
                        },
                    )

                for e in events:
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
                            "submitted_at": datetime.now(timezone.utc).isoformat(),
                            "state": "ENTRY_SUBMITTED",
                            "entry_order_id": resp.get("order_id"),
                            "entry_response": resp,
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

                # Research ledger: persist top nearest misses so we can later
                # calculate forward returns and tune thresholds from real data.
                for e in near_events[:5]:
                    append_bot_event(
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
