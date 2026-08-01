from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import deque
import json
import time
import shutil

SUMMARY_TXT = Path("/data/bot_output.txt")
ELIGIBILITY_STATUS_PATH = Path("/data/eligibility_status.json")
AUTH_HEALTH_LOG = Path("/data/auth_health_log.jsonl")
SIGNAL_PAPER_OUTCOMES_JSONL = Path("/data/signal_paper_outcomes_rebound_v1.jsonl")
NEAR_MISS_PAPER_JSONL = Path("/data/near_miss_paper_outcomes_rebound_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_B_JSONL = Path("/data/signal_paper_outcomes_strategy_b_rebound_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_D_JSONL = Path("/data/signal_paper_outcomes_strategy_d_090_rebound_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_C1_JSONL = Path("/data/signal_paper_outcomes_strategy_c1_trailing_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_C2_JSONL = Path("/data/signal_paper_outcomes_strategy_c2_no_high_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_C3_JSONL = Path("/data/signal_paper_outcomes_strategy_c3_lower_quotes_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_C4_JSONL = Path("/data/signal_paper_outcomes_strategy_c4_negative_slope_v1.jsonl")
NEAR_MISS_PAPER_C1_JSONL = Path("/data/near_miss_paper_outcomes_strategy_c1_trailing_v1.jsonl")
NEAR_MISS_PAPER_C2_JSONL = Path("/data/near_miss_paper_outcomes_strategy_c2_no_high_v1.jsonl")
NEAR_MISS_PAPER_C3_JSONL = Path("/data/near_miss_paper_outcomes_strategy_c3_lower_quotes_v1.jsonl")
NEAR_MISS_PAPER_C4_JSONL = Path("/data/near_miss_paper_outcomes_strategy_c4_negative_slope_v1.jsonl")
NEAR_MISS_PAPER_B_JSONL = Path("/data/near_miss_paper_outcomes_strategy_b_rebound_v1.jsonl")
NEAR_MISS_PAPER_D_JSONL = Path("/data/near_miss_paper_outcomes_strategy_d_090_rebound_v1.jsonl")
HISTORY_JSONL = Path("/data/bot_history.jsonl")
EVENTS_JSONL = Path("/data/bot_events.jsonl")
TRIGGER_OUTCOMES_JSONL = Path("/data/trigger_trade_outcomes.jsonl")

POLL_SECONDS = 30
MAX_HISTORY_ROWS = 5000

# Keep paper entry mechanics aligned with live_strategy_runner.py.
REBOUND_CONFIRMATION_PCT = 0.001
STRATEGY_B_REBOUND_CONFIRMATION_PCT = 0.002
RECOVERY_TARGET_FRACTION = 0.60
STOP_LOSS_FRACTION_BELOW_ENTRY = 0.05
STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY = 0.02
STRATEGY_D_FLASH_DROP_PCT = 0.90
STRATEGY_D_REBOUND_CONFIRMATION_PCT = STRATEGY_B_REBOUND_CONFIRMATION_PCT
STRATEGY_D_STOP_LOSS_FRACTION_BELOW_ENTRY = STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY
STOP_REPLAY_LEVELS_PCT = (1.0, 1.5, 2.0, 2.5, 3.0, 5.0)

# Strategy C forward-paper variants. They share Strategy B entries and its 2% protective stop.
# Start on the next full US market session so no pre-deployment trades are backfilled.
STRATEGY_C_FORWARD_START_UTC = "2026-07-28T13:30:00+00:00"
STRATEGY_C_ACTIVATION_GAIN_PCT = 0.30
STRATEGY_C1_PULLBACK_FROM_HIGH_PCT = 0.20
STRATEGY_C2_NO_NEW_HIGH_SECONDS = 30.0
STRATEGY_C3_LOWER_SAMPLES = 3
STRATEGY_C3_MIN_TOTAL_DECLINE_PCT = 0.10
STRATEGY_C4_SLOPE_WINDOW_SECONDS = 30.0
STRATEGY_C4_NEGATIVE_SLOPE_PCT_PER_MINUTE = -0.20

NY_TZ = ZoneInfo("America/New_York")

def event_strategy(event):
    """Legacy untagged events belong to Strategy A."""
    return str((event or {}).get("strategy_id") or "A").upper()



def is_rth_timestamp(value):
    """True only for Monday-Friday, 09:30 <= New York time < 16:00."""
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        et = ts.astimezone(NY_TZ)
        if et.weekday() >= 5:
            return False
        minutes = et.hour * 60 + et.minute
        return 9 * 60 + 30 <= minutes < 16 * 60
    except Exception:
        return False

def fmt_near(e):
    return (
        f"{e.get('symbol')} | score={float(e.get('miss_score', 999)):.2f} | "
        f"drop={float(e.get('flash_drop_pct', 0)):.2f}% | "
        f"gap={float(e.get('gap', 0)):.2f}% | "
        f"pre_ret={float(e.get('pre_return_pct', 0)):.2f}% | "
        f"pre_slope={float(e.get('pre_slope_pct_per_hour', 0)):.2f}%/hr | "
        f"r2={float(e.get('pre_r2', 0)):.2f} | "
        f"fails={e.get('failed', 'unknown')} | "
        f"price={float(e.get('price', 0)):.2f}"
    )

def _fmt_volume_metrics(obj):
    """Compact, readable flash/rebound volume fields for bot_output.txt."""
    obj = obj or {}
    parts = []
    if obj.get("volume_data_status_flash") == "OK":
        parts.extend([
            f"flash_vol_1m={_safe_float(obj.get('flash_volume_1m')):,.0f}",
            f"flash_vol_3m={_safe_float(obj.get('flash_volume_3m')):,.0f}",
            f"pre30_avg_1m={_safe_float(obj.get('avg_volume_1m_pre30')):,.0f}",
            f"flash_vol_ratio={_safe_float(obj.get('flash_volume_ratio')):.2f}x",
            f"flash_$vol_3m=${_safe_float(obj.get('flash_dollar_volume_3m')):,.0f}",
        ])
    elif obj.get("volume_data_status_flash"):
        parts.append(f"flash_vol_status={obj.get('volume_data_status_flash')}")

    if obj.get("volume_data_status_rebound") == "OK":
        parts.extend([
            f"rebound_vol_1m={_safe_float(obj.get('rebound_volume_1m')):,.0f}",
            f"rebound_vol_total={_safe_float(obj.get('rebound_volume_total')):,.0f}",
            f"rebound_vol_ratio={_safe_float(obj.get('rebound_volume_ratio')):.2f}x",
            f"rebound_$vol=${_safe_float(obj.get('rebound_dollar_volume_total')):,.0f}",
        ])
    elif obj.get("volume_data_status_rebound"):
        parts.append(f"rebound_vol_status={obj.get('volume_data_status_rebound')}")
    return " | ".join(parts)


def _volume_suffix(obj):
    text = _fmt_volume_metrics(obj)
    return f" | {text}" if text else ""


def load_recent_rows():
    if not HISTORY_JSONL.exists():
        return []
    rows = deque(maxlen=MAX_HISTORY_ROWS)
    with HISTORY_JSONL.open() as f:
        for raw in f:
            raw = raw.strip()
            if raw:
                try:
                    rows.append(json.loads(raw))
                except Exception:
                    pass
    return list(rows)

def load_recent_events():
    if not EVENTS_JSONL.exists():
        return []
    rows = deque(maxlen=MAX_HISTORY_ROWS)
    with EVENTS_JSONL.open() as f:
        for raw in f:
            raw = raw.strip()
            if raw:
                try:
                    rows.append(json.loads(raw))
                except Exception:
                    pass
    return list(rows)


def summarize_signal_event(e):
    sig = e.get("signal", {}) or {}
    ts = e.get("timestamp", "?")
    sym = e.get("symbol") or sig.get("symbol", "?")
    return (
        f"{ts} | {sym} | "
        f"drop={float(sig.get('flash_drop_pct', 0)):.2f}% "
        f"pre_ret={float(sig.get('pre_return_pct', 0)):.2f}% "
        f"pre_slope={float(sig.get('pre_slope_pct_per_hour', 0)):.2f}%/hr "
        f"entry={float(sig.get('entry_price', 0)):.2f} "
        f"target={float(sig.get('target_price', 0)):.2f} "
        f"stop={float(sig.get('stop_price', 0)):.2f}"
        + _volume_suffix(sig)
    )



def deep_find(obj, keys):
    if isinstance(keys, str):
        keys = {keys}
    else:
        keys = set(keys)

    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys:
                return v
        for v in obj.values():
            found = deep_find(v, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = deep_find(v, keys)
            if found is not None:
                return found
    return None


def trigger_key(e, strategy_id="A"):
    return f"{strategy_id}|{e.get('timestamp')}|{e.get('symbol')}"


def load_trigger_outcomes(path=SIGNAL_PAPER_OUTCOMES_JSONL):
    out = {}
    if not path.exists():
        return out
    try:
        with path.open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                    k = r.get("key")
                    if k:
                        out[k] = r
                except Exception:
                    pass
    except Exception:
        pass
    return out


def save_trigger_outcomes(outcomes, path=SIGNAL_PAPER_OUTCOMES_JSONL):
    try:
        tmp = path.with_suffix(".tmp")
        with tmp.open("w") as f:
            for r in outcomes.values():
                f.write(json.dumps(r) + "\n")
        tmp.replace(path)
    except Exception:
        pass


def signal_paper_outcome_lines(signal_events, max_items=100, strategy_id="A", outcomes_path=SIGNAL_PAPER_OUTCOMES_JSONL):
    """Paper-track every qualifying SIGNAL using its entry, target, stop and EOD exit."""
    try:
        import pandas as pd
        from zoneinfo import ZoneInfo
    except Exception as e:
        return [f"unavailable: import failed: {type(e).__name__}: {e}"]

    outcomes = load_trigger_outcomes(outcomes_path)

    # Defense in depth: ignore any historical SIGNAL outside RTH.
    signal_events = [
        e for e in signal_events
        if is_rth_timestamp(e.get("timestamp"))
    ]

    # Create one durable paper record for every qualifying signal.
    for e in signal_events:
        try:
            k = trigger_key(e, strategy_id)
            if k in outcomes:
                continue

            sig = e.get("signal", {}) or {}
            sym = e.get("symbol") or sig.get("symbol")
            entry = sig.get("entry_price")
            target = sig.get("target_price")
            stop = sig.get("stop_price")
            drop = sig.get("flash_drop_pct")

            if not sym or entry is None or target is None or stop is None:
                continue

            outcomes[k] = {
                "key": k,
                "strategy_id": strategy_id,
                "timestamp": e.get("timestamp"),
                "symbol": sym,

                "entry": float(entry),
                "target": float(target),
                "stop": float(stop),

                "flash_drop_pct": float(sig.get("flash_drop_pct", 0)),
                "pre_return_pct": float(sig.get("pre_return_pct", 0)),
                "pre_slope_pct_per_hour": float(sig.get("pre_slope_pct_per_hour", 0)),
                "pre_r2": float(sig.get("pre_r2", 0)),
                "actual_rebound_pct": sig.get("actual_rebound_pct"),
                "recovery_fraction_at_entry": sig.get("recovery_fraction_at_entry"),
                "remaining_upside_pct": sig.get("remaining_upside_pct"),
                "original_target_price": sig.get("original_target_price"),
                "original_flash_drop_pct": sig.get("original_flash_drop_pct"),
                **{
                    key: sig.get(key)
                    for key in (
                        "volume_data_status_flash", "flash_volume_1m", "flash_volume_3m",
                        "avg_volume_1m_pre30", "flash_volume_ratio",
                        "flash_dollar_volume_1m", "flash_dollar_volume_3m",
                        "volume_data_status_rebound", "rebound_volume_1m",
                        "rebound_volume_total", "rebound_volume_ratio",
                        "rebound_dollar_volume_1m", "rebound_dollar_volume_total",
                    )
                    if sig.get(key) is not None
                },

                "paper_notional": 1000.0,
                "status": "open",

                # Post-entry excursion tracking.
                "highest_price": float(entry),
                "highest_price_time": e.get("timestamp"),
                "lowest_price": float(entry),
                "lowest_price_time": e.get("timestamp"),
                "mfe_pct": 0.0,
                "mae_pct": 0.0,

                "exit_time": None,
                "exit_price": None,
                "exit_reason": None,
                "ret_pct": None,
                "pnl_usd": None,
                "last_checked": None,
            }
        except Exception:
            pass

    # Read only symbols that still have open paper trades.
    wanted_by_day = {}
    for rec in outcomes.values():
        if rec.get("status") == "closed" and rec.get("mfe_pct") is not None:
            continue
        ts = str(rec.get("timestamp", ""))
        sym = rec.get("symbol")
        if len(ts) >= 10 and sym:
            wanted_by_day.setdefault(ts[:10], set()).add(str(sym))

    tape_cache = {}
    for day, wanted in wanted_by_day.items():
        tape_path = Path("/data/tapes") / f"quotes_{day.replace('-', '')}.csv"
        if not tape_path.exists():
            tape_cache[day] = None
            continue

        try:
            parts = []
            for chunk in pd.read_csv(
                tape_path,
                usecols=["timestamp_utc", "symbol", "last_price"],
                dtype={"symbol": "string"},
                chunksize=50_000,
            ):
                chunk = chunk[chunk["symbol"].astype(str).isin(wanted)]
                if not chunk.empty:
                    parts.append(chunk)

            if not parts:
                tape_cache[day] = None
                continue

            df = pd.concat(parts, ignore_index=True).rename(
                columns={"timestamp_utc": "timestamp", "last_price": "price"}
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
            df["price"] = pd.to_numeric(df["price"], errors="coerce")
            df = df.dropna(subset=["timestamp", "symbol", "price"])

            et = df["timestamp"].dt.tz_convert(NY_TZ)
            minutes = et.dt.hour * 60 + et.dt.minute
            df = df[
                (et.dt.weekday < 5)
                & (minutes >= 9 * 60 + 30)
                & (minutes < 16 * 60)
            ]
            tape_cache[day] = df
        except Exception:
            tape_cache[day] = None

    # Resolve each trade at whichever occurs first: target, stop, or 15:55 ET.
    for rec in outcomes.values():
        if rec.get("status") == "closed" and rec.get("mfe_pct") is not None:
            continue

        try:
            ts = pd.Timestamp(rec["timestamp"])
            ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
            day = ts.strftime("%Y-%m-%d")
            df = tape_cache.get(day)
            if df is None or df.empty:
                continue

            sdf = df[
                (df["symbol"].astype(str) == str(rec["symbol"]))
                & (df["timestamp"] >= ts)
            ].sort_values("timestamp")
            if sdf.empty:
                continue

            target = float(rec["target"])
            stop = float(rec["stop"])
            entry = float(rec["entry"])
            exit_row = None
            reason = None

            highest_price = float(rec.get("highest_price", entry) or entry)
            lowest_price = float(rec.get("lowest_price", entry) or entry)
            highest_price_time = rec.get("highest_price_time") or rec.get("timestamp")
            lowest_price_time = rec.get("lowest_price_time") or rec.get("timestamp")

            for _, row in sdf.iterrows():
                px = float(row["price"])
                row_time = str(row["timestamp"])
                et = row["timestamp"].tz_convert(ZoneInfo("America/New_York"))

                if px > highest_price:
                    highest_price = px
                    highest_price_time = row_time
                if px < lowest_price:
                    lowest_price = px
                    lowest_price_time = row_time

                if px >= target:
                    exit_row, reason = row, "target"
                    break
                if px <= stop:
                    exit_row, reason = row, "stop"
                    break
                if (et.hour, et.minute) >= (15, 55):
                    exit_row, reason = row, "end"
                    break

            mfe_pct = (highest_price / entry - 1.0) * 100.0
            mae_pct = (lowest_price / entry - 1.0) * 100.0
            try:
                mfe_ts = pd.Timestamp(highest_price_time)
                mfe_ts = mfe_ts.tz_localize("UTC") if mfe_ts.tzinfo is None else mfe_ts.tz_convert("UTC")
                time_to_mfe_minutes = max(0.0, (mfe_ts - ts).total_seconds() / 60.0)
            except Exception:
                time_to_mfe_minutes = None
            stop_replay = {
                f"stop_{str(level).replace('.', '_')}pct_hit": mae_pct <= -level
                for level in STOP_REPLAY_LEVELS_PCT
            }
            rec.update({
                "highest_price": highest_price,
                "highest_price_time": highest_price_time,
                "lowest_price": lowest_price,
                "lowest_price_time": lowest_price_time,
                "mfe_pct": mfe_pct,
                "mae_pct": mae_pct,
                "time_to_mfe_minutes": time_to_mfe_minutes,
                "stop_replay": stop_replay,
                "last_checked": datetime.now(timezone.utc).isoformat(),
            })

            if exit_row is None:
                latest_row = sdf.iloc[-1]
                _update_open_mark_to_market(rec, latest_row["price"], latest_row["timestamp"])
                continue

            if reason == "target":
                exit_price = target
            elif reason == "stop":
                exit_price = stop
            else:
                exit_price = float(exit_row["price"])

            ret_pct = (exit_price / float(rec["entry"]) - 1) * 100
            rec.update({
                "status": "closed",
                "exit_time": str(exit_row["timestamp"]),
                "exit_price": exit_price,
                "exit_reason": reason,
                "ret_pct": ret_pct,
                "pnl_usd": float(rec.get("paper_notional", 1000.0)) * ret_pct / 100.0,
                "holding_minutes": max(
                    0.0, (exit_row["timestamp"] - ts).total_seconds() / 60.0
                ),
                "time_to_target_minutes": (
                    max(0.0, (exit_row["timestamp"] - ts).total_seconds() / 60.0)
                    if reason == "target" else None
                ),
                "last_checked": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass

    save_trigger_outcomes(outcomes, outcomes_path)

    rows = sorted(
        outcomes.values(),
        key=lambda r: str(r.get("timestamp", "")),
        reverse=True,
    )[:max_items]

    if not rows:
        return ["None"]

    lines = []
    for row in rows:
        try:
            base = (
                f"{row.get('timestamp')} | {row.get('symbol')} | "
                f"entry={float(row.get('entry', 0)):.2f} | "
                f"drop={float(row.get('flash_drop_pct', 0)):.2f}% | "
                f"pre_ret={float(row.get('pre_return_pct', 0)):.2f}% | "
                f"pre_slope={float(row.get('pre_slope_pct_per_hour', 0)):.2f}%/hr | "
                f"r2={float(row.get('pre_r2', 0)):.2f} | "
                f"target={float(row.get('target', 0)):.2f} | "
                f"stop={float(row.get('stop', 0)):.2f} | "
                f"high={float(row.get('highest_price', row.get('entry', 0))):.2f} | "
                f"MFE={float(row.get('mfe_pct', 0) or 0):+.2f}%"
                f" @ {row.get('highest_price_time')} | "
                f"low={float(row.get('lowest_price', row.get('entry', 0))):.2f} | "
                f"MAE={float(row.get('mae_pct', 0) or 0):+.2f}%"
                f" @ {row.get('lowest_price_time')} | "
                f"recovery_at_entry={float(row.get('recovery_fraction_at_entry', 0) or 0) * 100:.1f}% | "
                f"remaining_upside={float(row.get('remaining_upside_pct', 0) or 0):.2f}% | "
                f"time_to_MFE={float(row.get('time_to_mfe_minutes', 0) or 0):.1f}m | "
                f"stop_replay=" + ",".join(
                    f"{level:g}%:{'Y' if (row.get('stop_replay') or {}).get('stop_' + str(level).replace('.', '_') + 'pct_hit') else 'N'}"
                    for level in STOP_REPLAY_LEVELS_PCT
                )
                + _volume_suffix(row)
                + " | "
            )

            if row.get("status") == "closed":
                lines.append(
                    base
                    + f"exit_time={row.get('exit_time')} | "
                    + f"holding={float(row.get('holding_minutes', 0) or 0):.1f}m | "
                    + f"time_to_target={float(row.get('time_to_target_minutes', 0) or 0):.1f}m | "
                    + f"exit={float(row.get('exit_price', 0)):.2f} | "
                    + f"reason={row.get('exit_reason')} | "
                    + f"return={float(row.get('ret_pct', 0)):+.2f}% | "
                    + f"P/L_on_$1000={float(row.get('pnl_usd', 0)):+.2f}"
                )
            else:
                lines.append(base + _open_mark_to_market_suffix(row))
        except Exception as e:
            lines.append(
                f"{row.get('timestamp')} | {row.get('symbol')} | "
                f"render_error={type(e).__name__}: {e}"
            )

    return lines



_STRATEGY_C_TAPE_CACHE = {}


def _load_strategy_c_tape_day(day, wanted, pd):
    """Read a day's filtered tape once per file modification and symbol set."""
    tape_path = Path("/data/tapes") / f"quotes_{day.replace('-', '')}.csv"
    if not tape_path.exists():
        return None

    try:
        cache_key = (day, tuple(sorted(str(symbol) for symbol in wanted)))
        modified_ns = tape_path.stat().st_mtime_ns
        cached = _STRATEGY_C_TAPE_CACHE.get(cache_key)
        if cached and cached.get("modified_ns") == modified_ns:
            return cached.get("df")

        parts = []
        for chunk in pd.read_csv(
            tape_path,
            usecols=["timestamp_utc", "symbol", "last_price"],
            dtype={"symbol": "string"},
            chunksize=50_000,
        ):
            chunk = chunk[chunk["symbol"].astype(str).isin(wanted)]
            if not chunk.empty:
                parts.append(chunk)

        if not parts:
            result = None
        else:
            result = pd.concat(parts, ignore_index=True).rename(
                columns={"timestamp_utc": "timestamp", "last_price": "price"}
            )
            result["timestamp"] = pd.to_datetime(
                result["timestamp"], errors="coerce", utc=True
            )
            result["price"] = pd.to_numeric(result["price"], errors="coerce")
            result = result.dropna(subset=["timestamp", "symbol", "price"])
            et = result["timestamp"].dt.tz_convert(NY_TZ)
            minutes = et.dt.hour * 60 + et.dt.minute
            result = result[
                (et.dt.weekday < 5)
                & (minutes >= 9 * 60 + 30)
                & (minutes < 16 * 60)
            ]

        _STRATEGY_C_TAPE_CACHE[cache_key] = {
            "modified_ns": modified_ns,
            "df": result,
        }
        # Prevent unbounded growth if symbol sets change repeatedly.
        if len(_STRATEGY_C_TAPE_CACHE) > 20:
            oldest_key = next(iter(_STRATEGY_C_TAPE_CACHE))
            if oldest_key != cache_key:
                _STRATEGY_C_TAPE_CACHE.pop(oldest_key, None)
        return result
    except Exception:
        return None

def strategy_c_signal_paper_outcome_lines(
    signal_events,
    variant,
    max_items=100,
    outcomes_path=SIGNAL_PAPER_OUTCOMES_C1_JSONL,
):
    """Forward-paper Strategy C exits using Strategy B entries and quote tape.

    C1: exit after a configured pullback from the post-entry high.
    C2: exit after no new post-entry high for a configured number of seconds.
    C3: exit after configured consecutive lower quote samples and a minimum decline.
    C4: exit when the trailing price slope turns sufficiently negative.

    Every variant retains Strategy B's original 2% protective stop and 15:55 ET exit.
    Dynamic exits activate only after the trade first reaches the configured gain.
    """
    try:
        import pandas as pd
    except Exception as e:
        return [f"unavailable: import failed: {type(e).__name__}: {e}"]

    variant = str(variant).upper()
    if variant not in {"C1", "C2", "C3", "C4"}:
        return [f"unavailable: unknown Strategy C variant {variant}"]

    outcomes = load_trigger_outcomes(outcomes_path)
    start_ts = pd.Timestamp(STRATEGY_C_FORWARD_START_UTC)

    eligible_events = []
    for event in signal_events:
        try:
            event_ts = pd.Timestamp(event.get("timestamp"))
            event_ts = (
                event_ts.tz_localize("UTC")
                if event_ts.tzinfo is None
                else event_ts.tz_convert("UTC")
            )
            if is_rth_timestamp(event.get("timestamp")) and event_ts >= start_ts:
                eligible_events.append(event)
        except Exception:
            continue

    # Create one durable variant record for each Strategy B signal.
    for event in eligible_events:
        try:
            source_key = event.get("source_key")
            key = f"{variant}|{source_key}" if source_key else trigger_key(event, variant)
            if key in outcomes:
                continue

            sig = event.get("signal", {}) or {}
            symbol = event.get("symbol") or sig.get("symbol")
            entry = sig.get("entry_price")
            original_stop = sig.get("stop_price")
            if not symbol or entry is None:
                continue

            entry = float(entry)
            # Keep C variants aligned with Strategy B even if an older event lacks a stop.
            stop = (
                float(original_stop)
                if original_stop is not None
                else entry * (1.0 - STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY)
            )

            outcomes[key] = {
                "key": key,
                "strategy_id": variant,
                "source_strategy_id": "B",
                "source_record_type": event.get("source_record_type", "signal"),
                "source_key": source_key,
                "timestamp": event.get("timestamp"),
                "symbol": symbol,
                "entry": entry,
                "stop": stop,
                "baseline_target": float(sig.get("target_price", 0) or 0),
                "flash_drop_pct": float(sig.get("flash_drop_pct", 0) or 0),
                "pre_return_pct": float(sig.get("pre_return_pct", 0) or 0),
                "pre_slope_pct_per_hour": float(sig.get("pre_slope_pct_per_hour", 0) or 0),
                "pre_r2": float(sig.get("pre_r2", 0) or 0),
                "paper_notional": 1000.0,
                "status": "open",
                "activation_gain_pct": STRATEGY_C_ACTIVATION_GAIN_PCT,
                "dynamic_exit_activated": False,
                "activation_time": None,
                "highest_price": entry,
                "highest_price_time": event.get("timestamp"),
                "lowest_price": entry,
                "lowest_price_time": event.get("timestamp"),
                "mfe_pct": 0.0,
                "mae_pct": 0.0,
                "exit_time": None,
                "exit_price": None,
                "exit_reason": None,
                "ret_pct": None,
                "pnl_usd": None,
                "holding_minutes": None,
                "last_checked": None,
            }
        except Exception:
            pass

    wanted_by_day = {}
    for rec in outcomes.values():
        if rec.get("status") == "closed":
            continue
        ts = str(rec.get("timestamp", ""))
        symbol = rec.get("symbol")
        if len(ts) >= 10 and symbol:
            wanted_by_day.setdefault(ts[:10], set()).add(str(symbol))

    tape_cache = {
        day: _load_strategy_c_tape_day(day, wanted, pd)
        for day, wanted in wanted_by_day.items()
    }

    for rec in outcomes.values():
        if rec.get("status") == "closed":
            continue
        try:
            entry_ts = pd.Timestamp(rec["timestamp"])
            entry_ts = (
                entry_ts.tz_localize("UTC")
                if entry_ts.tzinfo is None
                else entry_ts.tz_convert("UTC")
            )
            day = entry_ts.strftime("%Y-%m-%d")
            df = tape_cache.get(day)
            if df is None or df.empty:
                continue

            trade_rows = df[
                (df["symbol"].astype(str) == str(rec["symbol"]))
                & (df["timestamp"] >= entry_ts)
            ].sort_values("timestamp")
            if trade_rows.empty:
                continue

            entry = float(rec["entry"])
            stop = float(rec["stop"])
            activation_price = entry * (1.0 + STRATEGY_C_ACTIVATION_GAIN_PCT / 100.0)
            highest_price = entry
            lowest_price = entry
            highest_price_time = entry_ts
            lowest_price_time = entry_ts
            activated = False
            activation_time = None
            exit_row = None
            reason = None
            recent_samples = []

            for _, row in trade_rows.iterrows():
                px = float(row["price"])
                row_ts = row["timestamp"]
                et = row_ts.tz_convert(NY_TZ)

                if px > highest_price:
                    highest_price = px
                    highest_price_time = row_ts

                if px < lowest_price:
                    lowest_price = px
                    lowest_price_time = row_ts

                # Protective rules always remain active.
                if px <= stop:
                    exit_row, reason = row, "stop"
                    break
                if (et.hour, et.minute) >= (15, 55):
                    exit_row, reason = row, "end"
                    break

                if not activated and px >= activation_price:
                    activated = True
                    activation_time = row_ts
                    # Reset the dynamic pattern at activation so pre-activation
                    # weakness cannot immediately force an exit.
                    recent_samples = [(row_ts, px)]
                    highest_price = max(highest_price, px)
                    highest_price_time = row_ts
                    continue

                if not activated:
                    continue

                recent_samples.append((row_ts, px))

                if variant == "C1":
                    pullback_pct = (highest_price - px) / highest_price * 100.0
                    if pullback_pct >= STRATEGY_C1_PULLBACK_FROM_HIGH_PCT:
                        exit_row, reason = row, "trail_pullback"
                        break

                elif variant == "C2":
                    seconds_without_high = (row_ts - highest_price_time).total_seconds()
                    if seconds_without_high >= STRATEGY_C2_NO_NEW_HIGH_SECONDS:
                        exit_row, reason = row, "no_new_high"
                        break

                elif variant == "C3":
                    needed = STRATEGY_C3_LOWER_SAMPLES + 1
                    if len(recent_samples) >= needed:
                        window = recent_samples[-needed:]
                        prices = [sample[1] for sample in window]
                        all_lower = all(
                            prices[i] < prices[i - 1]
                            for i in range(1, len(prices))
                        )
                        total_decline_pct = (prices[0] - prices[-1]) / prices[0] * 100.0
                        if all_lower and total_decline_pct >= STRATEGY_C3_MIN_TOTAL_DECLINE_PCT:
                            exit_row, reason = row, "consecutive_lower_quotes"
                            break

                elif variant == "C4":
                    cutoff = row_ts - pd.Timedelta(seconds=STRATEGY_C4_SLOPE_WINDOW_SECONDS)
                    recent_samples = [
                        sample for sample in recent_samples if sample[0] >= cutoff
                    ]
                    if len(recent_samples) >= 2:
                        first_ts, first_px = recent_samples[0]
                        elapsed_minutes = (row_ts - first_ts).total_seconds() / 60.0
                        if elapsed_minutes > 0:
                            slope_pct_per_minute = (
                                (px / first_px - 1.0) * 100.0 / elapsed_minutes
                            )
                            if slope_pct_per_minute <= STRATEGY_C4_NEGATIVE_SLOPE_PCT_PER_MINUTE:
                                exit_row, reason = row, "negative_slope"
                                rec["exit_slope_pct_per_minute"] = slope_pct_per_minute
                                break

            rec.update({
                "dynamic_exit_activated": activated,
                "activation_time": str(activation_time) if activation_time is not None else None,
                "highest_price": highest_price,
                "highest_price_time": str(highest_price_time),
                "lowest_price": lowest_price,
                "lowest_price_time": str(lowest_price_time),
                "mfe_pct": (highest_price / entry - 1.0) * 100.0,
                "mae_pct": (lowest_price / entry - 1.0) * 100.0,
                "last_checked": datetime.now(timezone.utc).isoformat(),
            })

            if exit_row is None:
                latest_row = trade_rows.iloc[-1]
                _update_open_mark_to_market(rec, latest_row["price"], latest_row["timestamp"])
                continue

            exit_price = stop if reason == "stop" else float(exit_row["price"])
            ret_pct = (exit_price / entry - 1.0) * 100.0
            rec.update({
                "status": "closed",
                "exit_time": str(exit_row["timestamp"]),
                "exit_price": exit_price,
                "exit_reason": reason,
                "ret_pct": ret_pct,
                "pnl_usd": float(rec.get("paper_notional", 1000.0)) * ret_pct / 100.0,
                "holding_minutes": max(
                    0.0, (exit_row["timestamp"] - entry_ts).total_seconds() / 60.0
                ),
            })
        except Exception:
            pass

    save_trigger_outcomes(outcomes, outcomes_path)

    rows = sorted(
        outcomes.values(),
        key=lambda row: str(row.get("timestamp", "")),
        reverse=True,
    )[:max_items]
    if not rows:
        return ["None"]

    lines = []
    for row in rows:
        try:
            base = (
                f"{row.get('timestamp')} | {row.get('symbol')} | "
                f"entry={float(row.get('entry', 0)):.2f} | "
                f"stop={float(row.get('stop', 0)):.2f} | "
                f"baseline_target={float(row.get('baseline_target', 0)):.2f} | "
                f"activated={'Y' if row.get('dynamic_exit_activated') else 'N'} | "
                f"activation_time={row.get('activation_time')} | "
                f"high={float(row.get('highest_price', row.get('entry', 0))):.2f} | "
                f"MFE={float(row.get('mfe_pct', 0) or 0):+.2f}% | "
                f"low={float(row.get('lowest_price', row.get('entry', 0))):.2f} | "
                f"MAE={float(row.get('mae_pct', 0) or 0):+.2f}% | "
            )
            if row.get("status") == "closed":
                slope_suffix = (
                    f" | exit_slope={float(row.get('exit_slope_pct_per_minute')):+.2f}%/min"
                    if row.get("exit_slope_pct_per_minute") is not None
                    else ""
                )
                lines.append(
                    base
                    + f"exit_time={row.get('exit_time')} | "
                    + f"holding={float(row.get('holding_minutes', 0) or 0):.1f}m | "
                    + f"exit={float(row.get('exit_price', 0)):.2f} | "
                    + f"reason={row.get('exit_reason')} | "
                    + f"return={float(row.get('ret_pct', 0)):+.2f}% | "
                    + f"P/L_on_$1000={float(row.get('pnl_usd', 0)):+.2f}"
                    + slope_suffix
                )
            else:
                lines.append(base + _open_mark_to_market_suffix(row))
        except Exception as e:
            lines.append(
                f"{row.get('timestamp')} | {row.get('symbol')} | "
                f"render_error={type(e).__name__}: {e}"
            )
    return lines

def strategy_c_near_miss_paper_outcome_lines(
    variant,
    max_items=100,
    outcomes_path=NEAR_MISS_PAPER_C1_JSONL,
    source_path=NEAR_MISS_PAPER_B_JSONL,
):
    """Apply a Strategy C exit variant to confirmed Strategy B near-miss entries.

    Strategy C changes only the exit. Entry qualification and rebound confirmation
    therefore remain owned by the Strategy B near-miss ledger. Pending candidates
    and candidates with no rebound confirmation are intentionally excluded.
    """
    source_records = load_near_miss_paper(source_path)
    pseudo_events = []

    for source_key, rec in source_records.items():
        try:
            entry = rec.get("entry")
            entry_time = rec.get("confirmation_time")
            if entry is None or not entry_time:
                continue
            if rec.get("status") in {"pending_rebound", "no_confirmation"}:
                continue
            if not is_rth_timestamp(entry_time):
                continue

            entry = float(entry)
            stop = rec.get("stop")
            if stop is None:
                stop = entry * (1.0 - STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY)

            pseudo_events.append({
                "event_type": "SIGNAL",
                "strategy_id": "B",
                "timestamp": entry_time,
                "symbol": rec.get("symbol"),
                "source_key": source_key,
                "source_record_type": "strategy_b_near_miss",
                "signal": {
                    "symbol": rec.get("symbol"),
                    "entry_price": entry,
                    "stop_price": float(stop),
                    "target_price": float(rec.get("target") or 0),
                    "flash_drop_pct": float(rec.get("flash_drop_pct", 0) or 0),
                    "pre_return_pct": float(rec.get("pre_return_pct", 0) or 0),
                    "pre_slope_pct_per_hour": float(
                        rec.get("pre_slope_pct_per_hour", 0) or 0
                    ),
                    "pre_r2": float(rec.get("pre_r2", 0) or 0),
                },
            })
        except Exception:
            continue

    return strategy_c_signal_paper_outcome_lines(
        pseudo_events,
        variant=variant,
        max_items=max_items,
        outcomes_path=outcomes_path,
    )


def trigger_trade_outcome_lines(max_items=100):
    """Render completed real broker trades, including MFE and MAE."""
    if not TRIGGER_OUTCOMES_JSONL.exists():
        return ["None"]

    rows = deque(maxlen=max_items)
    try:
        with TRIGGER_OUTCOMES_JSONL.open() as f:
            for raw in f:
                try:
                    row = json.loads(raw)
                    if row.get("symbol"):
                        rows.append(row)
                except Exception:
                    pass
    except Exception as e:
        return [f"unavailable: {type(e).__name__}: {e}"]

    if not rows:
        return ["None"]

    lines = []
    for r in reversed(rows):
        try:
            lines.append(
                f"{r.get('entry_fill_time')} | {r.get('symbol')} | "
                f"entry={float(r.get('entry_fill_price', 0)):.2f} | "
                f"exit_time={r.get('exit_fill_time')} | "
                f"exit={float(r.get('exit_fill_price', 0)):.2f} | "
                f"reason={r.get('exit_reason')} | "
                f"holding={float(r.get('holding_minutes', 0) or 0):.1f}m | "
                f"high={float(r.get('highest_price', 0)):.2f} | "
                f"MFE={float(r.get('mfe_pct', 0)):+.2f}% @ {r.get('mfe_at')} | "
                f"low={float(r.get('lowest_price', 0)):.2f} | "
                f"MAE={float(r.get('mae_pct', 0)):+.2f}% @ {r.get('mae_at')} | "
                f"recovery_at_entry={float(r.get('recovery_fraction_at_entry', 0) or 0) * 100:.1f}% | "
                f"remaining_upside={float(r.get('remaining_upside_pct', 0) or 0):.2f}% | "
                f"time_to_MFE={float(r.get('time_to_mfe_minutes', 0) or 0):.1f}m | "
                f"time_to_target={float(r.get('time_to_target_minutes', 0) or 0):.1f}m | "
                f"stop_replay=" + ",".join(
                    f"{level:g}%:{'Y' if (r.get('stop_replay') or {}).get('stop_' + str(level).replace('.', '_') + 'pct_hit') else 'N'}"
                    for level in STOP_REPLAY_LEVELS_PCT
                )
                + _volume_suffix(r)
                + " | "
                f"return={float(r.get('return_pct', 0)):+.2f}% | "
                f"P/L={float(r.get('realized_pnl', 0)):+.2f}"
            )
        except Exception as e:
            lines.append(f"{r.get('symbol', '?')} | render_error={type(e).__name__}: {e}")
    return lines


def summarize_trigger_event(e):
    sig = e.get("signal", {}) or {}
    return (
        f"{e.get('timestamp')} | {e.get('symbol')} | "
        f"buy_limit={float(e.get('buy_limit_price', 0)):.2f} | "
        f"entry={float(sig.get('entry_price', 0)):.2f} | "
        f"target={float(sig.get('target_price', 0)):.2f} | "
        f"stop={float(sig.get('stop_price', 0)):.2f} | "
        f"drop={float(sig.get('flash_drop_pct', 0)):.2f}% | "
        f"pre_ret={float(sig.get('pre_return_pct', 0)):.2f}% | "
        f"pre_slope={float(sig.get('pre_slope_pct_per_hour', 0)):.2f}%/hr"
        + _volume_suffix(sig)
    )

def summarize_execution_event(e):
    et = e.get("event_type", "UNKNOWN")
    sym = e.get("symbol", "?")
    qty = e.get("qty", "?")
    ts = e.get("timestamp", "?")
    if et in ("BUY_ATTEMPT", "SELL_ATTEMPT"):
        return f"{ts} | {et} | {sym} qty={qty}"
    if et in ("BUY_RESPONSE", "SELL_RESPONSE"):
        return f"{ts} | {et} | {sym} qty={qty} response={e.get('response')}"
    if et in ("BUY_ERROR", "SELL_ERROR"):
        return f"{ts} | {et} | {sym} qty={qty} error={e.get('exception_type')}: {e.get('error')}"
    return f"{ts} | {et} | {sym} qty={qty}"


def eligibility_health_lines():
    if not ELIGIBILITY_STATUS_PATH.exists():
        return [
            "ELIGIBILITY UNIVERSE",
            "status: UNKNOWN",
            f"status_file: {ELIGIBILITY_STATUS_PATH} MISSING",
        ]

    try:
        status = json.loads(ELIGIBILITY_STATUS_PATH.read_text())
        fallback = bool(status.get("used_fallback", False))
        age_days = status.get("age_days")
        age_text = "unknown" if age_days is None else f"{age_days} day" + ("" if age_days == 1 else "s")
        return [
            "ELIGIBILITY UNIVERSE",
            f"file: {status.get('filename', 'unknown')}",
            f"cache_date: {status.get('cache_date', 'unknown')}",
            f"symbols: {status.get('symbol_count', 'unknown')}",
            f"source: {'FALLBACK' if fallback else 'TODAY'}",
            f"age: {age_text}",
            f"collector_loaded: {status.get('loaded_at', 'unknown')}",
            f"status: {status.get('status', 'UNKNOWN')}",
        ]
    except Exception as exc:
        return [
            "ELIGIBILITY UNIVERSE",
            "status: ERROR",
            f"eligibility_status_error: {type(exc).__name__}: {exc}",
        ]


def storage_health_lines():
    try:
        usage = shutil.disk_usage("/data")
        total = usage.total
        used = usage.used
        free = usage.free
        pct = (used / total * 100) if total else 0

        def fmt(n):
            for unit in ["B", "K", "M", "G", "T"]:
                if n < 1024:
                    return f"{n:.0f}{unit}"
                n /= 1024
            return f"{n:.0f}P"

        return [
            "STORAGE HEALTH",
            f"data_used: {fmt(used)} / {fmt(total)}",
            f"data_available: {fmt(free)}",
            f"data_use_percent: {pct:.1f}%",
        ]
    except Exception as e:
        return ["STORAGE HEALTH", f"storage_error: {e}"]

def _one_token_health_lines(label, token_path):
    token_path = Path(token_path)
    if not token_path.exists():
        return [label, f"token_file: {token_path} MISSING", "auth_status: BROKEN"]

    try:
        token_data = json.loads(token_path.read_text())
        token = token_data.get("token", {}) if isinstance(token_data.get("token"), dict) else {}

        created = float(token_data.get("creation_timestamp", 0) or 0)
        expires = float(token.get("expires_at", 0) or token_data.get("expires_at", 0) or 0)
        has_access_token = bool(token.get("access_token") or token_data.get("access_token"))
        has_refresh_token = bool(token.get("refresh_token") or token_data.get("refresh_token"))
        account_present = bool(token_data.get("account_id") or token_data.get("account_hash"))
        now = time.time()

        minutes_left = (expires - now) / 60 if expires else -999999
        access_status = "EXPIRED" if minutes_left <= 0 else ("WARNING" if minutes_left < 10 else "OK")

        if has_refresh_token:
            auth_status = "REFRESHABLE" if access_status != "EXPIRED" else "ACCESS_EXPIRED_BUT_REFRESH_TOKEN_PRESENT"
        else:
            auth_status = "ACCESS_ONLY_EXPIRED_NEEDS_MANUAL_REGEN" if access_status == "EXPIRED" else "ACCESS_ONLY_OK"

        lines = [
            label,
            f"token_file: {token_path}",
            f"token_file_modified_utc: {datetime.fromtimestamp(token_path.stat().st_mtime, timezone.utc).isoformat()}",
            f"token_created_utc: {datetime.fromtimestamp(created, timezone.utc).isoformat() if created else 'unknown'}",
            f"access_token_expires_utc: {datetime.fromtimestamp(expires, timezone.utc).isoformat() if expires else 'unknown'}",
            f"access_token_minutes_left: {minutes_left:.1f}",
            f"has_access_token: {has_access_token}",
            f"has_refresh_token: {has_refresh_token}",
            f"account_present: {account_present}",
            f"access_status: {access_status}",
            f"auth_status: {auth_status}",
            f"auto_refresh: {'YES_VIA_SCHWAB_PY' if has_refresh_token else 'NO_REFRESH_TOKEN'}",
            f"refresh_note: {'access token refreshes automatically on next authenticated SDK request' if has_refresh_token else 'manual token regeneration required when access expires'}",
        ]

        if created:
            lines += [
                f"manual_reauth_due_utc: {datetime.fromtimestamp(created + 7*24*3600, timezone.utc).isoformat()}",
                f"manual_reauth_time_left: {((created + 7*24*3600) - now)/86400:.2f} days",
            ]

        return lines

    except Exception as e:
        return [label, f"token_parse_error: {e}", "auth_status: BROKEN"]



def append_auth_health_snapshot():
    try:
        snap = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "market_minutes_left": token_minutes_left("/data/schwab_token.json"),
            "trading_minutes_left": token_minutes_left("/data/schwab_trade_token.json"),
            "storage_used_percent": storage_used_percent(),
        }

        snap["market_status"] = (
            "EXPIRED" if snap["market_minutes_left"] < 0 else
            "WARNING" if snap["market_minutes_left"] < 10 else
            "OK"
        )
        snap["trading_status"] = (
            "EXPIRED" if snap["trading_minutes_left"] < 0 else
            "WARNING" if snap["trading_minutes_left"] < 10 else
            "OK"
        )

        with AUTH_HEALTH_LOG.open("a") as f:
            f.write(json.dumps(snap) + "\n")
    except Exception:
        pass


def auth_downtime_history_lines():
    try:
        if not AUTH_HEALTH_LOG.exists():
            return ["No auth history yet."]

        today = datetime.now(timezone.utc).date().isoformat()
        rows = []
        with AUTH_HEALTH_LOG.open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                    if str(r.get("timestamp", ""))[:10] == today:
                        rows.append(r)
                except Exception:
                    pass

        if not rows:
            return ["No auth history today."]

        lines = []
        for prefix, min_key, status_key in [
            ("market_data", "market_minutes_left", "market_status"),
            ("trading", "trading_minutes_left", "trading_status"),
        ]:
            vals = [float(r.get(min_key, 999999)) for r in rows]
            statuses = [r.get(status_key, "unknown") for r in rows]

            warnings = sum(1 for st in statuses if st == "WARNING")
            expired = sum(1 for st in statuses if st == "EXPIRED")
            worst = min(vals) if vals else 999999

            bad_rows = [
                r for r in rows
                if r.get(status_key) in ("WARNING", "EXPIRED")
            ]
            last_bad = bad_rows[-1].get("timestamp") if bad_rows else "none"

            lines.append(
                f"{prefix} | snapshots={len(rows)} | warnings={warnings} | "
                f"expired={expired} | worst_minutes_left={worst:.1f} | last_bad={last_bad}"
            )

        storage_vals = [float(r.get("storage_used_percent", 0)) for r in rows]
        lines.append(
            f"storage | worst_used_percent={max(storage_vals):.1f}% | "
            f"latest_used_percent={storage_vals[-1]:.1f}%"
        )

        return lines
    except Exception as e:
        return [f"auth history unavailable: {type(e).__name__}: {e}"]

def token_health_lines():
    market = _one_token_health_lines("SCHWAB MARKET DATA HEALTH", "/data/schwab_token.json")
    trading = _one_token_health_lines("SCHWAB TRADING HEALTH", "/data/schwab_trade_token.json")

    def status(lines):
        joined = "\n".join(lines)
        if "access_status: OK" in joined or "access_status: WARNING" in joined:
            return "OK"
        if "auth_status: ACCESS_EXPIRED_BUT_REFRESH_TOKEN_PRESENT" in joined:
            return "REFRESHABLE"
        return "BROKEN"

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    tape = Path("/data/tapes") / f"quotes_{today}.csv"
    if not tape.exists() or tape.stat().st_size == 0:
        quote_status = "NO_TAPE"
    else:
        tape_age = max(0, time.time() - tape.stat().st_mtime)
        quote_status = "OK" if tape_age <= 120 else f"STALE ({tape_age:.0f}s)"

    capabilities = [
        "BOT CAPABILITIES",
        f"quote_collection: {quote_status}",
        "signal_generation: OK",
        f"order_placement: {status(trading)}",
    ]

    return market + [""] + trading + [""] + capabilities


def near_miss_paper_key(e, strategy_id="A"):
    return f"{strategy_id}|{e.get('seen_at')}|{e.get('symbol')}|{float(e.get('price', 0)):.6f}"


def load_near_miss_paper(path=NEAR_MISS_PAPER_JSONL):
    out = {}
    if not path.exists():
        return out
    try:
        with path.open() as f:
            for line in f:
                try:
                    row = json.loads(line)
                    key = row.get("key")
                    if key:
                        out[key] = row
                except Exception:
                    pass
    except Exception:
        pass
    return out


def save_near_miss_paper(outcomes, path=NEAR_MISS_PAPER_JSONL):
    try:
        tmp = path.with_suffix(".tmp")
        with tmp.open("w") as f:
            for row in outcomes.values():
                f.write(json.dumps(row) + "\n")
        tmp.replace(path)
    except Exception:
        pass


def near_miss_paper_lines(top_events, max_items=25, strategy_id="A", outcomes_path=NEAR_MISS_PAPER_JSONL, rebound_confirmation_pct=None, stop_loss_fraction=None):
    """Paper-track near misses using the live strategy's rebound entry logic.

    A near miss is first recorded as pending. Its paper entry occurs only after
    price rises REBOUND_CONFIRMATION_PCT above the running post-detection low.
    Target, stop, holding time and P/L are then calculated from that confirmed
    entry, matching the signal paper trade mechanics.
    """
    try:
        import pandas as pd
    except Exception as e:
        return [f"unavailable: import failed: {type(e).__name__}: {e}"]

    outcomes = load_near_miss_paper(outcomes_path)
    rebound_confirmation_pct = (
        REBOUND_CONFIRMATION_PCT if rebound_confirmation_pct is None else rebound_confirmation_pct
    )
    stop_loss_fraction = (
        STOP_LOSS_FRACTION_BELOW_ENTRY if stop_loss_fraction is None else stop_loss_fraction
    )

    # Defense in depth: only paper-track near misses first observed in RTH.
    top_events = [
        event for event in top_events
        if is_rth_timestamp(event.get("seen_at"))
    ]

    # Freeze each distinct dashboard event once. Repeated symbols at different
    # timestamps remain separate paper candidates.
    for event in top_events:
        try:
            key = near_miss_paper_key(event, strategy_id)
            if key in outcomes:
                rec = outcomes[key]
                rec.setdefault("pre_return_pct", float(event.get("pre_return_pct", 0) or 0))
                rec.setdefault(
                    "pre_slope_pct_per_hour",
                    float(event.get("pre_slope_pct_per_hour", 0) or 0),
                )
                rec.setdefault("pre_r2", float(event.get("pre_r2", 0) or 0))
                rec.setdefault("failed", event.get("failed", "unknown"))
                rec.setdefault("gap", float(event.get("gap", 0) or 0))
                rec.setdefault("miss_score", float(event.get("miss_score", 999) or 999))
                continue

            detection_price = float(event.get("price", 0))
            drop = float(event.get("flash_drop_pct", 0))
            if detection_price <= 0 or drop >= 100:
                continue

            flash_start = detection_price / (1 - drop / 100.0)

            outcomes[key] = {
                "key": key,
                "strategy_id": strategy_id,
                "date": str(event.get("seen_at", ""))[:10],
                "timestamp": event.get("seen_at"),
                "detection_time": event.get("seen_at"),
                "symbol": event.get("symbol"),
                "detection_price": detection_price,
                "flash_start_price": flash_start,
                "flash_drop_pct": drop,
                "pre_return_pct": float(event.get("pre_return_pct", 0) or 0),
                "pre_slope_pct_per_hour": float(
                    event.get("pre_slope_pct_per_hour", 0) or 0
                ),
                "pre_r2": float(event.get("pre_r2", 0) or 0),
                "failed": event.get("failed", "unknown"),
                "gap": float(event.get("gap", 0) or 0),
                "miss_score": float(event.get("miss_score", 999) or 999),
                "required_rebound_pct": rebound_confirmation_pct * 100,
                "running_low": detection_price,
                "confirmation_time": None,
                "confirmation_delay_seconds": None,
                "actual_rebound_pct": None,
                "entry": None,
                "target": None,
                "stop": None,
                "paper_notional": 1000.0,
                "status": "pending_rebound",
                "highest_price": None,
                "highest_price_time": None,
                "lowest_price": None,
                "lowest_price_time": None,
                "mfe_pct": None,
                "mae_pct": None,
                "exit_time": None,
                "exit_price": None,
                "exit_reason": None,
                "ret_pct": None,
                "pnl_usd": None,
            }
        except Exception:
            pass

    wanted_by_day = {}
    for rec in outcomes.values():
        if rec.get("status") in ("closed", "no_confirmation"):
            continue
        ts = str(rec.get("detection_time") or rec.get("timestamp", ""))
        sym = rec.get("symbol")
        if len(ts) >= 10 and sym:
            wanted_by_day.setdefault(ts[:10], set()).add(str(sym))

    tape_cache = {}
    for day, wanted in wanted_by_day.items():
        tape_path = Path("/data/tapes") / f"quotes_{day.replace('-', '')}.csv"
        if not tape_path.exists():
            tape_cache[day] = None
            continue
        try:
            parts = []
            for chunk in pd.read_csv(
                tape_path,
                usecols=["timestamp_utc", "symbol", "last_price"],
                dtype={"symbol": "string"},
                chunksize=50_000,
            ):
                chunk = chunk[chunk["symbol"].astype(str).isin(wanted)]
                if not chunk.empty:
                    parts.append(chunk)
            if not parts:
                tape_cache[day] = None
                continue
            df = pd.concat(parts, ignore_index=True).rename(
                columns={"timestamp_utc": "timestamp", "last_price": "price"}
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
            df["price"] = pd.to_numeric(df["price"], errors="coerce")
            df = df.dropna(subset=["timestamp", "symbol", "price"])

            et = df["timestamp"].dt.tz_convert(NY_TZ)
            minutes = et.dt.hour * 60 + et.dt.minute
            df = df[
                (et.dt.weekday < 5)
                & (minutes >= 9 * 60 + 30)
                & (minutes < 16 * 60)
            ]
            tape_cache[day] = df
        except Exception:
            tape_cache[day] = None

    for rec in outcomes.values():
        if rec.get("status") in ("closed", "no_confirmation"):
            continue
        try:
            detection_ts = pd.Timestamp(
                rec.get("detection_time") or rec.get("timestamp")
            )
            detection_ts = (
                detection_ts.tz_localize("UTC")
                if detection_ts.tzinfo is None
                else detection_ts.tz_convert("UTC")
            )
            day = detection_ts.strftime("%Y-%m-%d")
            df = tape_cache.get(day)
            if df is None or df.empty:
                continue

            sdf = df[
                (df["symbol"].astype(str) == str(rec["symbol"]))
                & (df["timestamp"] >= detection_ts)
            ].sort_values("timestamp")
            if sdf.empty:
                continue

            # New records wait for the same running-low rebound as live entries.
            # Legacy open records that already have an entry are allowed to
            # continue resolving without rewriting historical paper results.
            if rec.get("entry") is None:
                running_low = float(
                    rec.get("running_low")
                    or rec.get("detection_price")
                    or sdf.iloc[0]["price"]
                )
                confirmation_row = None

                for _, row in sdf.iterrows():
                    px = float(row["price"])
                    if px < running_low:
                        running_low = px

                    rebound_fraction = (px / running_low) - 1.0
                    if rebound_fraction >= rebound_confirmation_pct:
                        confirmation_row = row
                        rec["actual_rebound_pct"] = rebound_fraction * 100
                        break

                    et = row["timestamp"].tz_convert(NY_TZ)
                    if (et.hour, et.minute) >= (15, 55):
                        rec.update({
                            "status": "no_confirmation",
                            "running_low": running_low,
                            "exit_time": str(row["timestamp"]),
                            "exit_reason": "no_rebound_confirmation",
                            "ret_pct": 0.0,
                            "pnl_usd": 0.0,
                        })
                        break

                rec["running_low"] = running_low

                if rec.get("status") == "no_confirmation":
                    continue
                if confirmation_row is None:
                    continue

                entry = float(confirmation_row["price"])
                flash_start = float(rec["flash_start_price"])
                target = entry + RECOVERY_TARGET_FRACTION * (flash_start - entry)
                stop = entry * (1 - stop_loss_fraction)
                confirmation_ts = confirmation_row["timestamp"]

                rec.update({
                    "status": "open",
                    "confirmation_time": str(confirmation_ts),
                    "highest_price": entry,
                    "highest_price_time": str(confirmation_ts),
                    "lowest_price": entry,
                    "lowest_price_time": str(confirmation_ts),
                    "mfe_pct": 0.0,
                    "mae_pct": 0.0,
                    "confirmation_delay_seconds": max(
                        0.0, (confirmation_ts - detection_ts).total_seconds()
                    ),
                    "entry": entry,
                    "target": target,
                    "stop": stop,
                    "confirmed_flash_drop_pct": (
                        (flash_start - entry) / flash_start * 100
                    ),
                })

            entry_ts = pd.Timestamp(rec.get("confirmation_time") or rec["timestamp"])
            entry_ts = (
                entry_ts.tz_localize("UTC")
                if entry_ts.tzinfo is None
                else entry_ts.tz_convert("UTC")
            )
            trade_rows = sdf[sdf["timestamp"] >= entry_ts]
            if trade_rows.empty:
                continue

            target = float(rec["target"])
            stop = float(rec["stop"])
            entry = float(rec["entry"])
            exit_row = None
            reason = None

            highest_price = float(rec.get("highest_price", entry) or entry)
            lowest_price = float(rec.get("lowest_price", entry) or entry)
            highest_price_time = rec.get("highest_price_time") or str(entry_ts)
            lowest_price_time = rec.get("lowest_price_time") or str(entry_ts)

            for _, row in trade_rows.iterrows():
                px = float(row["price"])
                row_time = str(row["timestamp"])
                et = row["timestamp"].tz_convert(NY_TZ)

                if px > highest_price:
                    highest_price = px
                    highest_price_time = row_time
                if px < lowest_price:
                    lowest_price = px
                    lowest_price_time = row_time

                if px >= target:
                    exit_row, reason = row, "target"
                    break
                if px <= stop:
                    exit_row, reason = row, "stop"
                    break
                if (et.hour, et.minute) >= (15, 55):
                    exit_row, reason = row, "end"
                    break

            rec.update({
                "highest_price": highest_price,
                "highest_price_time": highest_price_time,
                "lowest_price": lowest_price,
                "lowest_price_time": lowest_price_time,
                "mfe_pct": (highest_price / entry - 1.0) * 100.0,
                "mae_pct": (lowest_price / entry - 1.0) * 100.0,
            })

            if exit_row is None:
                latest_row = trade_rows.iloc[-1]
                _update_open_mark_to_market(rec, latest_row["price"], latest_row["timestamp"])
                continue

            exit_price = (
                target if reason == "target"
                else stop if reason == "stop"
                else float(exit_row["price"])
            )
            ret_pct = (exit_price / float(rec["entry"]) - 1) * 100
            rec.update({
                "status": "closed",
                "exit_time": str(exit_row["timestamp"]),
                "exit_price": exit_price,
                "exit_reason": reason,
                "ret_pct": ret_pct,
                "pnl_usd": float(rec.get("paper_notional", 1000.0)) * ret_pct / 100.0,
                "holding_minutes": max(
                    0.0, (exit_row["timestamp"] - entry_ts).total_seconds() / 60.0
                ),
            })
        except Exception:
            pass

    save_near_miss_paper(outcomes, outcomes_path)

    rows = sorted(
        outcomes.values(),
        key=lambda r: str(r.get("detection_time") or r.get("timestamp", "")),
        reverse=True,
    )[:max_items]
    if not rows:
        return ["None"]

    lines = []
    for row in rows:
        try:
            detection_price = float(
                row.get("detection_price")
                or row.get("entry")
                or 0
            )
            base = (
                f"{row.get('detection_time') or row.get('timestamp')} | {row.get('symbol')} | "
                f"detected={detection_price:.2f} | "
                f"drop={float(row.get('flash_drop_pct', 0)):.2f}% | "
                f"pre_ret={float(row.get('pre_return_pct', 0)):.2f}% | "
                f"pre_slope={float(row.get('pre_slope_pct_per_hour', 0)):.2f}%/hr | "
                f"r2={float(row.get('pre_r2', 0)):.2f} | "
                f"gap={float(row.get('gap', 0)):.2f}% | "
                f"fails={row.get('failed', 'unknown')} | "
                f"score={float(row.get('miss_score', 999)):.2f} | "
            )

            if row.get("status") == "pending_rebound":
                lines.append(
                    base
                    + f"low={float(row.get('running_low', detection_price)):.2f} | "
                    + f"required_rebound={float(row.get('required_rebound_pct', rebound_confirmation_pct * 100)):.2f}% | "
                    + "status=PENDING_REBOUND"
                )
            elif row.get("status") == "no_confirmation":
                lines.append(
                    base
                    + f"low={float(row.get('running_low', detection_price)):.2f} | "
                    + "status=NO_REBOUND_CONFIRMATION | P/L_on_$1000=+0.00"
                )
            else:
                base += (
                    f"confirmed={row.get('confirmation_time', row.get('timestamp'))} | "
                    f"delay={float(row.get('confirmation_delay_seconds', 0) or 0):.1f}s | "
                    f"low={float(row.get('running_low', 0) or 0):.2f} | "
                    f"rebound={float(row.get('actual_rebound_pct', 0) or 0):.3f}% | "
                    f"entry={float(row.get('entry', 0)):.2f} | "
                    f"target={float(row.get('target', 0)):.2f} | "
                    f"stop={float(row.get('stop', 0)):.2f} | "
                    f"high={float(row.get('highest_price', row.get('entry', 0)) or row.get('entry', 0)):.2f} | "
                    f"MFE={float(row.get('mfe_pct', 0) or 0):+.2f}%"
                    f" @ {row.get('highest_price_time')} | "
                    f"low={float(row.get('lowest_price', row.get('entry', 0)) or row.get('entry', 0)):.2f} | "
                    f"MAE={float(row.get('mae_pct', 0) or 0):+.2f}%"
                    f" @ {row.get('lowest_price_time')} | "
                )
                if row.get("status") == "closed":
                    lines.append(
                        base
                        + f"exit_time={row.get('exit_time')} | "
                        + f"holding={float(row.get('holding_minutes', 0) or 0):.1f}m | "
                        + f"exit={float(row.get('exit_price', 0)):.2f} | "
                        + f"reason={row.get('exit_reason')} | "
                        + f"return={float(row.get('ret_pct', 0)):+.2f}% | "
                        + f"P/L_on_$1000={float(row.get('pnl_usd', 0)):+.2f}"
                    )
                else:
                    lines.append(base + _open_mark_to_market_suffix(row))
        except Exception as e:
            lines.append(
                f"{row.get('timestamp')} | {row.get('symbol')} | "
                f"render_error={type(e).__name__}: {e}"
            )
    return lines


REBOUND_EVENT_TYPES = {
    "PENDING_REBOUND_CREATED",
    "PENDING_REBOUND_NEW_LOW",
    "PENDING_REBOUND_WAITING",
    "REBOUND_CONFIRMED",
    "PENDING_REBOUND_CANCELLED_NOT_QUALIFIED",
    "PENDING_REBOUND_CANCELLED_ENTRY_CUTOFF",
    "PENDING_REBOUND_TIMEOUT",
}


def load_today_rebound_events(today):
    """Load every rebound-lifecycle event for today without the 5,000-row cap."""
    if not EVENTS_JSONL.exists():
        return []
    rows = []
    try:
        with EVENTS_JSONL.open() as f:
            for raw in f:
                try:
                    event = json.loads(raw)
                except Exception:
                    continue
                if (
                    event.get("event_type") in REBOUND_EVENT_TYPES
                    and str(event.get("timestamp", "")).startswith(today)
                    and is_rth_timestamp(event.get("timestamp"))
                ):
                    rows.append(event)
    except Exception:
        return []
    return rows


def _safe_float(value, default=None):
    try:
        return float(value)
    except Exception:
        return default


def _update_open_mark_to_market(rec, price, price_time):
    """Store a lightweight mark-to-market snapshot for an open paper trade."""
    try:
        entry = float(rec.get("entry"))
        current_price = float(price)
        if entry <= 0 or current_price <= 0:
            return
        current_ret_pct = (current_price / entry - 1.0) * 100.0
        notional = float(rec.get("paper_notional", 1000.0) or 1000.0)
        rec.update({
            "current_price": current_price,
            "current_price_time": str(price_time),
            "current_ret_pct": current_ret_pct,
            "current_pnl_usd": notional * current_ret_pct / 100.0,
        })
    except Exception:
        pass


def _open_mark_to_market_suffix(row):
    """Render the latest cached quote and unrealized P/L for an open record."""
    current_price = _safe_float((row or {}).get("current_price"))
    current_ret_pct = _safe_float((row or {}).get("current_ret_pct"))
    current_pnl_usd = _safe_float((row or {}).get("current_pnl_usd"))
    if current_price is None or current_ret_pct is None or current_pnl_usd is None:
        return "current=UNAVAILABLE | status=OPEN (P/L unavailable)"
    return (
        f"current={current_price:.2f} | "
        f"current_return={current_ret_pct:+.2f}% | "
        f"current_P/L_on_$1000={current_pnl_usd:+.2f} | "
        f"current_at={row.get('current_price_time')} | status=OPEN ({current_pnl_usd:+.2f})"
    )


def rebound_lifecycle(rebound_events):
    """Return active candidates, completed outcomes, and summary statistics."""
    active = {}
    outcomes = []

    for event in sorted(rebound_events, key=lambda e: str(e.get("timestamp", ""))):
        event_type = event.get("event_type")
        symbol = event.get("symbol")
        if not symbol:
            continue

        if event_type == "PENDING_REBOUND_CREATED":
            active[symbol] = {
                "symbol": symbol,
                "created_at": event.get("timestamp"),
                "last_update": event.get("timestamp"),
                "current_price": event.get("current_price"),
                "lowest_price": event.get("current_price"),
                "rebound_pct": 0.0,
                "highest_rebound_pct": 0.0,
                "required_rebound_pct": event.get("required_rebound_pct"),
                "waiting_seconds": 0.0,
                "signal": event.get("signal", {}) or {},
            }
            continue

        candidate = active.get(symbol)

        if event_type in ("PENDING_REBOUND_NEW_LOW", "PENDING_REBOUND_WAITING"):
            if candidate is None:
                candidate = {
                    "symbol": symbol,
                    "created_at": event.get("pending_created_at") or event.get("timestamp"),
                    "signal": event.get("signal", {}) or {},
                }
                active[symbol] = candidate
            candidate["last_update"] = event.get("timestamp")
            candidate["current_price"] = event.get("current_price", event.get("new_low"))
            candidate["lowest_price"] = event.get(
                "lowest_price", event.get("new_low", candidate.get("lowest_price"))
            )
            candidate["rebound_pct"] = event.get("rebound_pct", candidate.get("rebound_pct"))
            candidate["highest_rebound_pct"] = event.get(
                "highest_rebound_pct", candidate.get("highest_rebound_pct", 0.0)
            )
            candidate["required_rebound_pct"] = event.get(
                "required_rebound_pct", candidate.get("required_rebound_pct")
            )
            candidate["waiting_seconds"] = event.get(
                "waiting_seconds", candidate.get("waiting_seconds")
            )
            if event.get("signal"):
                candidate["signal"] = event.get("signal")
            continue

        if event_type in (
            "REBOUND_CONFIRMED",
            "PENDING_REBOUND_CANCELLED_NOT_QUALIFIED",
            "PENDING_REBOUND_CANCELLED_ENTRY_CUTOFF",
            "PENDING_REBOUND_TIMEOUT",
        ):
            base = candidate or {
                "symbol": symbol,
                "created_at": event.get("pending_created_at"),
                "signal": event.get("original_signal") or event.get("signal") or {},
            }
            outcome = dict(base)
            outcome.update({
                "event_type": event_type,
                "finished_at": event.get("timestamp"),
                "current_price": event.get("entry_price", event.get("current_price", base.get("current_price"))),
                "lowest_price": event.get("lowest_price", base.get("lowest_price")),
                "rebound_pct": event.get("rebound_pct", base.get("rebound_pct")),
                "highest_rebound_pct": event.get(
                    "highest_rebound_pct", base.get("highest_rebound_pct", 0.0)
                ),
                "waiting_seconds": event.get("waiting_seconds", base.get("waiting_seconds")),
                "reason": event.get("reason"),
                "signal": event.get("signal") or base.get("signal") or {},
            })
            outcomes.append(outcome)
            active.pop(symbol, None)

    created_count = sum(
        1 for event in rebound_events
        if event.get("event_type") == "PENDING_REBOUND_CREATED"
    )
    confirmed = [x for x in outcomes if x.get("event_type") == "REBOUND_CONFIRMED"]
    cancelled = [
        x for x in outcomes
        if x.get("event_type") == "PENDING_REBOUND_CANCELLED_NOT_QUALIFIED"
    ]
    cutoff = [
        x for x in outcomes
        if x.get("event_type") == "PENDING_REBOUND_CANCELLED_ENTRY_CUTOFF"
    ]
    timeout = [x for x in outcomes if x.get("event_type") == "PENDING_REBOUND_TIMEOUT"]
    completed_count = len(outcomes)
    confirmation_rate = (
        len(confirmed) / completed_count * 100.0 if completed_count else 0.0
    )
    delays = [
        _safe_float(x.get("waiting_seconds"))
        for x in confirmed
        if _safe_float(x.get("waiting_seconds")) is not None
    ]

    stats = {
        "created": created_count,
        "active": len(active),
        "completed": completed_count,
        "confirmed": len(confirmed),
        "cancelled_not_qualified": len(cancelled),
        "entry_cutoff": len(cutoff),
        "timeout": len(timeout),
        "confirmation_rate": confirmation_rate,
        "average_confirmation_seconds": sum(delays) / len(delays) if delays else None,
    }
    return list(active.values()), outcomes, stats


def pending_rebound_lines(active_candidates):
    if not active_candidates:
        return ["None"]
    lines = []
    for row in sorted(
        active_candidates,
        key=lambda x: str(x.get("created_at", "")),
        reverse=True,
    ):
        sig = row.get("signal", {}) or {}
        lines.append(
            f"{row.get('created_at')} | {row.get('symbol')} | "
            f"drop={_safe_float(sig.get('flash_drop_pct'), 0.0):.2f}% | "
            f"pre_ret={_safe_float(sig.get('pre_return_pct'), 0.0):.2f}% | "
            f"pre_slope={_safe_float(sig.get('pre_slope_pct_per_hour'), 0.0):.2f}%/hr | "
            f"current={_safe_float(row.get('current_price'), 0.0):.2f} | "
            f"running_low={_safe_float(row.get('lowest_price'), 0.0):.2f} | "
            f"rebound={_safe_float(row.get('rebound_pct'), 0.0):.3f}% | "
            f"required={_safe_float(row.get('required_rebound_pct'), REBOUND_CONFIRMATION_PCT * 100):.3f}% | "
            f"age={_safe_float(row.get('waiting_seconds'), 0.0):.1f}s"
            + _volume_suffix(sig)
        )
    return lines


def rebound_outcome_lines(outcomes, max_items=100):
    if not outcomes:
        return ["None"]
    labels = {
        "REBOUND_CONFIRMED": "CONFIRMED",
        "PENDING_REBOUND_CANCELLED_NOT_QUALIFIED": "FAILED_NOT_QUALIFIED",
        "PENDING_REBOUND_CANCELLED_ENTRY_CUTOFF": "FAILED_ENTRY_CUTOFF",
        "PENDING_REBOUND_TIMEOUT": "FAILED_TIMEOUT",
    }
    lines = []
    for row in sorted(
        outcomes,
        key=lambda x: str(x.get("finished_at", "")),
        reverse=True,
    )[:max_items]:
        sig = row.get("signal", {}) or {}
        lines.append(
            f"{row.get('finished_at')} | {row.get('symbol')} | "
            f"outcome={labels.get(row.get('event_type'), row.get('event_type'))} | "
            f"reason={row.get('reason') or 'none'} | "
            f"drop={_safe_float(sig.get('flash_drop_pct'), 0.0):.2f}% | "
            f"low={_safe_float(row.get('lowest_price'), 0.0):.2f} | "
            f"final_rebound={_safe_float(row.get('rebound_pct'), 0.0):.3f}% | "
            f"max_rebound={_safe_float(row.get('highest_rebound_pct'), 0.0):.3f}% | "
            f"wait={_safe_float(row.get('waiting_seconds'), 0.0):.1f}s"
            + _volume_suffix(sig)
        )
    return lines


def rebound_summary_lines(stats):
    avg = stats.get("average_confirmation_seconds")
    return [
        f"Pending created today: {stats.get('created', 0)}",
        f"Currently pending: {stats.get('active', 0)}",
        f"Completed outcomes: {stats.get('completed', 0)}",
        f"Confirmed: {stats.get('confirmed', 0)}",
        f"Failed — no longer qualified: {stats.get('cancelled_not_qualified', 0)}",
        f"Failed — entry cutoff: {stats.get('entry_cutoff', 0)}",
        f"Failed — timeout: {stats.get('timeout', 0)}",
        f"Confirmation rate among completed: {stats.get('confirmation_rate', 0.0):.1f}%",
        f"Average confirmation delay: {avg:.1f}s" if avg is not None else "Average confirmation delay: n/a",
    ]

def main():
    print("leaderboard_writer.py starting lightweight mode", flush=True)

    while True:
        try:
            rows = load_recent_rows()
            events = load_recent_events()
            latest = rows[-1] if rows else None
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            today_rows = [
                r for r in rows
                if r.get("date") == today
                and is_rth_timestamp(r.get("timestamp"))
            ]
            today_events = [
                e for e in events
                if str(e.get("timestamp", "")).startswith(today)
                and is_rth_timestamp(e.get("timestamp"))
            ]
            signal_events_today = [e for e in today_events if e.get("event_type") == "SIGNAL" and event_strategy(e) == "A"]
            signal_events_b_today = [e for e in today_events if e.get("event_type") == "SIGNAL" and event_strategy(e) == "B"]
            signal_events_d_today = [e for e in today_events if e.get("event_type") == "SIGNAL" and event_strategy(e) == "D"]
            rebound_events_today = [e for e in load_today_rebound_events(today) if event_strategy(e) == "A"]
            rebound_events_b_today = [e for e in load_today_rebound_events(today) if event_strategy(e) == "B"]
            rebound_events_d_today = [e for e in load_today_rebound_events(today) if event_strategy(e) == "D"]
            active_rebounds, rebound_outcomes, rebound_stats = rebound_lifecycle(
                rebound_events_today
            )
            active_rebounds_b, rebound_outcomes_b, rebound_stats_b = rebound_lifecycle(
                rebound_events_b_today
            )
            active_rebounds_d, rebound_outcomes_d, rebound_stats_d = rebound_lifecycle(
                rebound_events_d_today
            )
            trigger_events_today = [e for e in today_events if e.get("event_type") == "ENTRY_TRIGGER_OCO_ATTEMPT" and event_strategy(e) == "A"]
            execution_events_today = [e for e in today_events if e.get("event_type") in ("BUY_ATTEMPT", "BUY_RESPONSE", "BUY_ERROR", "SELL_ATTEMPT", "SELL_RESPONSE", "SELL_ERROR", "ENTRY_CANCEL_REQUESTED", "ENTRY_FILL_CONFIRMED", "TRIGGER_TRADE_CLOSED")]

            top_today = []
            triggers_today = 0
            for r in today_rows:
                triggers_today = max(triggers_today, int(r.get("total_triggers_today", 0) or 0))
                for e in r.get("latest_nearest", []) or []:
                    x = dict(e)
                    x["seen_at"] = r.get("timestamp")
                    top_today.append(x)

            top_today = sorted(top_today, key=lambda e: float(e.get("miss_score", 999)))[:5]

            top_b_today = []
            for e in today_events:
                if e.get("event_type") == "NEAR_MISS" and event_strategy(e) == "B":
                    c = dict(e.get("candidate", {}) or {})
                    c["seen_at"] = e.get("timestamp")
                    top_b_today.append(c)
            top_b_today = sorted(top_b_today, key=lambda e: float(e.get("miss_score", 999)))[:5]

            top_d_today = []
            for e in today_events:
                if e.get("event_type") == "NEAR_MISS" and event_strategy(e) == "D":
                    c = dict(e.get("candidate", {}) or {})
                    c["seen_at"] = e.get("timestamp")
                    top_d_today.append(c)
            top_d_today = sorted(top_d_today, key=lambda e: float(e.get("miss_score", 999)))[:5]

            by_day = {}
            for r in rows:
                d = r.get("date", "unknown")
                by_day.setdefault(d, {"best": None, "triggers": 0})
                by_day[d]["triggers"] = max(by_day[d]["triggers"], int(r.get("total_triggers_today", 0) or 0))
                for e in r.get("latest_nearest", []) or []:
                    if by_day[d]["best"] is None or float(e.get("miss_score", 999)) < float(by_day[d]["best"].get("miss_score", 999)):
                        by_day[d]["best"] = dict(e)

            append_auth_health_snapshot()

            lines = [
                "BOT OUTPUT",
                f"Last update: {datetime.now(timezone.utc).isoformat()}",
                f"Status: {latest.get('status', 'unknown') if latest else 'unknown'}",
                "",
                *eligibility_health_lines(),
                "",
                *token_health_lines(),
                "",
                *storage_health_lines(),
                "",
                "AUTH DOWNTIME / WARNING HISTORY TODAY",
                *auth_downtime_history_lines(),
                "",
                "STRATEGY A — ACTIVE THRESHOLDS",
                "flash_drop >= 1.00%",
                "pre_return >= 0.25%",
                "pre_slope >= 0.50%/hr",
                "max_flash_drop <= 12.00%",
                "",
                "STRATEGY A — LATEST NEAREST MISSES",
            ]

            if latest and latest.get("latest_nearest"):
                for e in latest["latest_nearest"][:5]:
                    lines.append(fmt_near(e))
            else:
                lines.append("None")

            lines += ["", "STRATEGY A — TOP 5 NEAREST MISSES TODAY"]
            if top_today:
                for e in top_today:
                    lines.append(f"{fmt_near(e)} | seen={e.get('seen_at')}")
            else:
                lines.append("None")

            lines += ["", "STRATEGY A — TOP 5 NEAR-MISS PAPER OUTCOMES — PAPER ONLY"]
            for line in near_miss_paper_lines(top_today, max_items=25, strategy_id="A", outcomes_path=NEAR_MISS_PAPER_JSONL):
                lines.append(line)

            lines += ["", "STRATEGY A — PENDING REBOUND CANDIDATES — QUALIFIED, AWAITING CONFIRMATION"]
            for line in pending_rebound_lines(active_rebounds):
                lines.append(line)

            lines += ["", "STRATEGY A — REBOUND OUTCOMES TODAY"]
            for line in rebound_outcome_lines(rebound_outcomes, max_items=100):
                lines.append(line)

            lines += ["", "STRATEGY A — REBOUND SUMMARY TODAY"]
            lines.extend(rebound_summary_lines(rebound_stats))

            lines += ["", "STRATEGY A — TRIGGERS TODAY"]
            if latest and latest.get("latest_triggers"):
                for e in latest["latest_triggers"][:10]:
                    lines.append(str(e))
            else:
                lines.append("None")
            lines.append(f"Total triggers today: {triggers_today}")

            lines += ["", "STRATEGY A — TRIGGER TRADE LEDGER TODAY"]
            if trigger_events_today:
                for e in trigger_events_today[-50:]:
                    lines.append(summarize_trigger_event(e))
            else:
                lines.append("None")

            lines += ["", "STRATEGY A — REAL TRIGGER TRADE OUTCOMES"]
            for line in trigger_trade_outcome_lines(max_items=100):
                lines.append(line)

            lines += ["", "STRATEGY A — SIGNAL PAPER OUTCOMES"]
            for line in signal_paper_outcome_lines(
                [
                    e for e in events
                    if e.get("event_type") == "SIGNAL"
                    and event_strategy(e) == "A"
                    and is_rth_timestamp(e.get("timestamp"))
                ],
                max_items=100,
                strategy_id="A",
                outcomes_path=SIGNAL_PAPER_OUTCOMES_JSONL,
            ):
                lines.append(line)

            lines += ["", "STRATEGY A — FULL SIGNAL LEDGER TODAY"]
            if signal_events_today:
                for e in signal_events_today[-20:]:
                    lines.append(summarize_signal_event(e))
            else:
                lines.append("None")

            lines += ["", "========================", "STRATEGY B — PAPER SHADOW", "========================"]
            lines += ["", "STRATEGY B — ACTIVE THRESHOLDS"]
            lines += [
                "flash_drop >= 1.00%",
                "pre_return >= 0.25%",
                "pre_slope >= 0.50%/hr",
                "max_flash_drop <= 12.00%",
                "rebound_confirmation >= 0.20%",
                "stop_loss = 2.00%",
                "live_order_placement: DISABLED",
            ]

            lines += ["", "STRATEGY B — TOP 5 NEAREST MISSES TODAY"]
            if top_b_today:
                for e in top_b_today:
                    lines.append(f"{fmt_near(e)} | seen={e.get('seen_at')}")
            else:
                lines.append("None")

            lines += ["", "STRATEGY B — TOP 5 NEAR-MISS PAPER OUTCOMES — PAPER ONLY"]
            for line in near_miss_paper_lines(
                top_b_today, max_items=25, strategy_id="B", outcomes_path=NEAR_MISS_PAPER_B_JSONL,
                rebound_confirmation_pct=STRATEGY_B_REBOUND_CONFIRMATION_PCT,
                stop_loss_fraction=STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY,
            ):
                lines.append(line)

            lines += ["", "STRATEGY B — PENDING REBOUND CANDIDATES — QUALIFIED, AWAITING CONFIRMATION"]
            lines.extend(pending_rebound_lines(active_rebounds_b))

            lines += ["", "STRATEGY B — REBOUND OUTCOMES TODAY"]
            lines.extend(rebound_outcome_lines(rebound_outcomes_b, max_items=100))

            lines += ["", "STRATEGY B — REBOUND SUMMARY TODAY"]
            lines.extend(rebound_summary_lines(rebound_stats_b))

            lines += ["", "STRATEGY B — SIGNAL PAPER OUTCOMES"]
            for line in signal_paper_outcome_lines(
                [
                    e for e in events
                    if e.get("event_type") == "SIGNAL"
                    and event_strategy(e) == "B"
                    and is_rth_timestamp(e.get("timestamp"))
                ],
                max_items=100,
                strategy_id="B",
                outcomes_path=SIGNAL_PAPER_OUTCOMES_B_JSONL,
            ):
                lines.append(line)

            lines += ["", "STRATEGY B — FULL SIGNAL LEDGER TODAY"]
            if signal_events_b_today:
                for e in signal_events_b_today[-20:]:
                    lines.append(summarize_signal_event(e))
            else:
                lines.append("None")

            lines += ["", "========================", "STRATEGY D — STRATEGY B CLONE / 0.90% FLASH", "========================"]
            lines += ["", "STRATEGY D — ACTIVE THRESHOLDS"]
            lines += [
                "flash_drop >= 0.90%",
                "pre_return >= 0.25%",
                "pre_slope >= 0.50%/hr",
                "max_flash_drop <= 12.00%",
                "rebound_confirmation >= 0.20%",
                "stop_loss = 2.00%",
                "live_order_placement: DISABLED",
            ]

            lines += ["", "STRATEGY D — TOP 5 NEAREST MISSES TODAY"]
            if top_d_today:
                for e in top_d_today:
                    lines.append(f"{fmt_near(e)} | seen={e.get('seen_at')}")
            else:
                lines.append("None")

            lines += ["", "STRATEGY D — TOP 5 NEAR-MISS PAPER OUTCOMES — PAPER ONLY"]
            for line in near_miss_paper_lines(
                top_d_today, max_items=25, strategy_id="D", outcomes_path=NEAR_MISS_PAPER_D_JSONL,
                rebound_confirmation_pct=STRATEGY_D_REBOUND_CONFIRMATION_PCT,
                stop_loss_fraction=STRATEGY_D_STOP_LOSS_FRACTION_BELOW_ENTRY,
            ):
                lines.append(line)

            lines += ["", "STRATEGY D — PENDING REBOUND CANDIDATES — QUALIFIED, AWAITING CONFIRMATION"]
            lines.extend(pending_rebound_lines(active_rebounds_d))

            lines += ["", "STRATEGY D — REBOUND OUTCOMES TODAY"]
            lines.extend(rebound_outcome_lines(rebound_outcomes_d, max_items=100))

            lines += ["", "STRATEGY D — REBOUND SUMMARY TODAY"]
            lines.extend(rebound_summary_lines(rebound_stats_d))

            lines += ["", "STRATEGY D — SIGNAL PAPER OUTCOMES"]
            for line in signal_paper_outcome_lines(
                [
                    e for e in events
                    if e.get("event_type") == "SIGNAL"
                    and event_strategy(e) == "D"
                    and is_rth_timestamp(e.get("timestamp"))
                ],
                max_items=100,
                strategy_id="D",
                outcomes_path=SIGNAL_PAPER_OUTCOMES_D_JSONL,
            ):
                lines.append(line)

            lines += ["", "STRATEGY D — FULL SIGNAL LEDGER TODAY"]
            if signal_events_d_today:
                for e in signal_events_d_today[-20:]:
                    lines.append(summarize_signal_event(e))
            else:
                lines.append("None")

            strategy_b_all_signals = [
                e for e in events
                if e.get("event_type") == "SIGNAL"
                and event_strategy(e) == "B"
                and is_rth_timestamp(e.get("timestamp"))
            ]

            lines += ["", "========================", "STRATEGY C — FORWARD PAPER EXIT RESEARCH", "========================"]
            lines += [
                f"forward_start_utc: {STRATEGY_C_FORWARD_START_UTC}",
                "entry_source: Strategy B SIGNAL entries",
                f"activation_gain: +{STRATEGY_C_ACTIVATION_GAIN_PCT:.2f}%",
                "protective_stop: Strategy B 2.00% stop",
                "end_of_day_exit: 15:55 ET",
                "live_order_placement: DISABLED",
            ]

            lines += ["", "STRATEGY C1 — 0.20% TRAILING PULLBACK AFTER ACTIVATION — B SIGNALS"]
            lines.extend(strategy_c_signal_paper_outcome_lines(
                strategy_b_all_signals,
                variant="C1",
                max_items=100,
                outcomes_path=SIGNAL_PAPER_OUTCOMES_C1_JSONL,
            ))
            lines += ["", "STRATEGY C1 — B NEAR-MISS ENTRIES — PAPER ONLY"]
            lines.extend(strategy_c_near_miss_paper_outcome_lines(
                variant="C1", max_items=100, outcomes_path=NEAR_MISS_PAPER_C1_JSONL
            ))

            lines += ["", "STRATEGY C2 — NO NEW HIGH FOR 30 SECONDS AFTER ACTIVATION — B SIGNALS"]
            lines.extend(strategy_c_signal_paper_outcome_lines(
                strategy_b_all_signals,
                variant="C2",
                max_items=100,
                outcomes_path=SIGNAL_PAPER_OUTCOMES_C2_JSONL,
            ))
            lines += ["", "STRATEGY C2 — B NEAR-MISS ENTRIES — PAPER ONLY"]
            lines.extend(strategy_c_near_miss_paper_outcome_lines(
                variant="C2", max_items=100, outcomes_path=NEAR_MISS_PAPER_C2_JSONL
            ))

            lines += ["", "STRATEGY C3 — 3 LOWER QUOTES / >=0.10% DECLINE AFTER ACTIVATION — B SIGNALS"]
            lines.extend(strategy_c_signal_paper_outcome_lines(
                strategy_b_all_signals,
                variant="C3",
                max_items=100,
                outcomes_path=SIGNAL_PAPER_OUTCOMES_C3_JSONL,
            ))
            lines += ["", "STRATEGY C3 — B NEAR-MISS ENTRIES — PAPER ONLY"]
            lines.extend(strategy_c_near_miss_paper_outcome_lines(
                variant="C3", max_items=100, outcomes_path=NEAR_MISS_PAPER_C3_JSONL
            ))

            lines += ["", "STRATEGY C4 — 30-SECOND SLOPE <= -0.20%/MIN AFTER ACTIVATION — B SIGNALS"]
            lines.extend(strategy_c_signal_paper_outcome_lines(
                strategy_b_all_signals,
                variant="C4",
                max_items=100,
                outcomes_path=SIGNAL_PAPER_OUTCOMES_C4_JSONL,
            ))
            lines += ["", "STRATEGY C4 — B NEAR-MISS ENTRIES — PAPER ONLY"]
            lines.extend(strategy_c_near_miss_paper_outcome_lines(
                variant="C4", max_items=100, outcomes_path=NEAR_MISS_PAPER_C4_JSONL
            ))

            near_miss_events_today = [e for e in today_events if e.get("event_type") == "NEAR_MISS" and event_strategy(e) == "A"]
            lines += ["", "STRATEGY A — NEAR MISS EVENTS TODAY"]
            if near_miss_events_today:
                for e in near_miss_events_today[-10:]:
                    c = e.get("candidate", {}) or {}
                    lines.append(
                        f"{e.get('timestamp')} | {e.get('symbol')} | "
                        f"score={float(c.get('miss_score', 999)):.2f} | "
                        f"drop={float(c.get('flash_drop_pct', 0)):.2f}% | "
                        f"gap={float(c.get('gap', 0)):.2f}% | "
                        f"pre_ret={float(c.get('pre_return_pct', 0)):.2f}% | "
                        f"pre_slope={float(c.get('pre_slope_pct_per_hour', 0)):.2f}%/hr | "
                        f"fails={c.get('failed', 'unknown')} | "
                        f"price={float(c.get('price', 0)):.2f}"
                    )
                lines.append(f"Total near-miss events today: {len(near_miss_events_today)}")
            else:
                lines.append("None")

            signal_by_day = {}
            for e in events:
                if (
                    e.get("event_type") != "SIGNAL"
                    or not is_rth_timestamp(e.get("timestamp"))
                ):
                    continue
                ts = str(e.get("timestamp", ""))
                d = ts[:10] if len(ts) >= 10 else "unknown"
                signal_by_day.setdefault(d, []).append(e)

            lines += ["", "MULTI-DAY SIGNAL LEDGER"]
            if signal_by_day:
                for d in sorted(signal_by_day.keys())[-10:]:
                    lines.append(f"{d} | signals={len(signal_by_day[d])}")
                    for e in signal_by_day[d][-5:]:
                        lines.append("  " + summarize_signal_event(e))
            else:
                lines.append("No signal events yet.")

            lines += ["", "ORDER / EXECUTION EVENTS TODAY"]
            if execution_events_today:
                for e in execution_events_today[-20:]:
                    lines.append(summarize_execution_event(e))
            else:
                lines.append("None")

            exec_by_day = {}
            for e in events:
                ts = str(e.get("timestamp", ""))
                d = ts[:10] if len(ts) >= 10 else "unknown"
                et = e.get("event_type")
                exec_by_day.setdefault(d, {"buy_attempts": 0, "buy_responses": 0, "buy_errors": 0, "sell_attempts": 0, "sell_responses": 0, "sell_errors": 0})
                if et == "BUY_ATTEMPT":
                    exec_by_day[d]["buy_attempts"] += 1
                elif et == "BUY_RESPONSE":
                    exec_by_day[d]["buy_responses"] += 1
                elif et == "BUY_ERROR":
                    exec_by_day[d]["buy_errors"] += 1
                elif et == "SELL_ATTEMPT":
                    exec_by_day[d]["sell_attempts"] += 1
                elif et == "SELL_RESPONSE":
                    exec_by_day[d]["sell_responses"] += 1
                elif et == "SELL_ERROR":
                    exec_by_day[d]["sell_errors"] += 1

            lines += ["", "MULTI-DAY EXECUTION SUMMARY"]
            if exec_by_day:
                for d in sorted(exec_by_day.keys())[-10:]:
                    x = exec_by_day[d]
                    lines.append(
                        f"{d} | buy_attempts={x['buy_attempts']} buy_responses={x['buy_responses']} "
                        f"buy_errors={x['buy_errors']} sell_attempts={x['sell_attempts']} "
                        f"sell_responses={x['sell_responses']} sell_errors={x['sell_errors']}"
                    )
            else:
                lines.append("No execution events yet.")


            trigger_by_day = {}
            for e in events:
                if e.get("event_type") != "ENTRY_TRIGGER_OCO_ATTEMPT":
                    continue
                d = str(e.get("timestamp", ""))[:10]
                trigger_by_day.setdefault(d, []).append(e)

            lines += ["", "MULTI-DAY TRIGGER LEDGER"]
            if trigger_by_day:
                for d in sorted(trigger_by_day.keys())[-10:]:
                    lines.append(f"{d} | triggers={len(trigger_by_day[d])}")
                    for e in trigger_by_day[d][-20:]:
                        lines.append("  " + summarize_trigger_event(e))
            else:
                lines.append("No trigger events yet.")

            lines += ["", "MULTI-DAY SUMMARY"]
            if by_day:
                for d in sorted(by_day.keys())[-10:]:
                    b = by_day[d]["best"]
                    if b:
                        lines.append(
                            f"{d} | best={b.get('symbol')} score={float(b.get('miss_score', 999)):.2f} "
                            f"drop={float(b.get('flash_drop_pct', 0)):.2f}% "
                            f"gap={float(b.get('gap', 0)):.2f}% | "
                            f"pre_ret={float(b.get('pre_return_pct', 0)):.2f}% "
                            f"pre_slope={float(b.get('pre_slope_pct_per_hour', 0)):.2f}%/hr "
                            f"fails={b.get('failed', 'unknown')} | triggers={by_day[d]['triggers']}"
                        )
                    else:
                        lines.append(f"{d} | no nearest data | triggers={by_day[d]['triggers']}")
            else:
                lines.append("No history yet.")

            SUMMARY_TXT.write_text("\n".join(lines) + "\n")

        except Exception as e:
            print(f"leaderboard error: {type(e).__name__}: {e}", flush=True)

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
