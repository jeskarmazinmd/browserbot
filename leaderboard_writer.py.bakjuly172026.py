from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import deque
import json
import time
import shutil

SUMMARY_TXT = Path("/data/bot_output.txt")
AUTH_HEALTH_LOG = Path("/data/auth_health_log.jsonl")
SIGNAL_PAPER_OUTCOMES_JSONL = Path("/data/signal_paper_outcomes.jsonl")
NEAR_MISS_PAPER_JSONL = Path("/data/near_miss_paper_outcomes.jsonl")
HISTORY_JSONL = Path("/data/bot_history.jsonl")
EVENTS_JSONL = Path("/data/bot_events.jsonl")

POLL_SECONDS = 30
MAX_HISTORY_ROWS = 5000

NY_TZ = ZoneInfo("America/New_York")


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


def trigger_key(e):
    return f"{e.get('timestamp')}|{e.get('symbol')}"


def load_trigger_outcomes():
    out = {}
    if not SIGNAL_PAPER_OUTCOMES_JSONL.exists():
        return out
    try:
        with SIGNAL_PAPER_OUTCOMES_JSONL.open() as f:
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


def save_trigger_outcomes(outcomes):
    try:
        tmp = SIGNAL_PAPER_OUTCOMES_JSONL.with_suffix(".tmp")
        with tmp.open("w") as f:
            for r in outcomes.values():
                f.write(json.dumps(r) + "\n")
        tmp.replace(SIGNAL_PAPER_OUTCOMES_JSONL)
    except Exception:
        pass


def signal_paper_outcome_lines(signal_events, max_items=100):
    """Paper-track every qualifying SIGNAL using its entry, target, stop and EOD exit."""
    try:
        import pandas as pd
        from zoneinfo import ZoneInfo
    except Exception as e:
        return [f"unavailable: import failed: {type(e).__name__}: {e}"]

    outcomes = load_trigger_outcomes()

    # Defense in depth: ignore any historical SIGNAL outside RTH.
    signal_events = [
        e for e in signal_events
        if is_rth_timestamp(e.get("timestamp"))
    ]

    # Create one durable paper record for every qualifying signal.
    for e in signal_events:
        try:
            k = trigger_key(e)
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
                "timestamp": e.get("timestamp"),
                "symbol": sym,

                "entry": float(entry),
                "target": float(target),
                "stop": float(stop),

                "flash_drop_pct": float(sig.get("flash_drop_pct", 0)),
                "pre_return_pct": float(sig.get("pre_return_pct", 0)),
                "pre_slope_pct_per_hour": float(sig.get("pre_slope_pct_per_hour", 0)),
                "pre_r2": float(sig.get("pre_r2", 0)),

                "paper_notional": 1000.0,
                "status": "open",
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
        if rec.get("status") == "closed":
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
        if rec.get("status") == "closed":
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
            exit_row = None
            reason = None

            for _, row in sdf.iterrows():
                px = float(row["price"])
                et = row["timestamp"].tz_convert(ZoneInfo("America/New_York"))

                if px >= target:
                    exit_row, reason = row, "target"
                    break
                if px <= stop:
                    exit_row, reason = row, "stop"
                    break
                if (et.hour, et.minute) >= (15, 55):
                    exit_row, reason = row, "end"
                    break

            if exit_row is None:
                rec["last_checked"] = datetime.now(timezone.utc).isoformat()
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
                "last_checked": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass

    save_trigger_outcomes(outcomes)

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
                f"target={float(row.get('target', 0)):.2f} | "
                f"stop={float(row.get('stop', 0)):.2f} | "
            )

            if row.get("status") == "closed":
                lines.append(
                    base
                    + f"exit={float(row.get('exit_price', 0)):.2f} | "
                    + f"reason={row.get('exit_reason')} | "
                    + f"return={float(row.get('ret_pct', 0)):+.2f}% | "
                    + f"P/L_on_$1000={float(row.get('pnl_usd', 0)):+.2f}"
                )
            else:
                lines.append(base + "status=OPEN")
        except Exception as e:
            lines.append(
                f"{row.get('timestamp')} | {row.get('symbol')} | "
                f"render_error={type(e).__name__}: {e}"
            )

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


def near_miss_paper_key(e):
    return f"{e.get('seen_at')}|{e.get('symbol')}|{float(e.get('price', 0)):.6f}"


def load_near_miss_paper():
    out = {}
    if not NEAR_MISS_PAPER_JSONL.exists():
        return out
    try:
        with NEAR_MISS_PAPER_JSONL.open() as f:
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


def save_near_miss_paper(outcomes):
    try:
        tmp = NEAR_MISS_PAPER_JSONL.with_suffix(".tmp")
        with tmp.open("w") as f:
            for row in outcomes.values():
                f.write(json.dumps(row) + "\n")
        tmp.replace(NEAR_MISS_PAPER_JSONL)
    except Exception:
        pass


def near_miss_paper_lines(top_events, max_items=25):
    """Track the dashboard's top-five near misses as $1,000 paper trades only."""
    try:
        import pandas as pd
        from zoneinfo import ZoneInfo
    except Exception as e:
        return [f"unavailable: import failed: {type(e).__name__}: {e}"]

    outcomes = load_near_miss_paper()

    # Defense in depth: only paper-track near misses first observed in RTH.
    top_events = [
        event for event in top_events
        if is_rth_timestamp(event.get("seen_at"))
    ]

    # Freeze each distinct dashboard event once. Repeated symbols at different
    # timestamps remain separate paper trades.
    for event in top_events:
        try:
            key = near_miss_paper_key(event)
            if key in outcomes:
                continue

            entry = float(event.get("price", 0))
            drop = float(event.get("flash_drop_pct", 0))
            if entry <= 0 or drop >= 100:
                continue

            flash_start = entry / (1 - drop / 100.0)
            target = entry + 0.60 * (flash_start - entry)
            stop = entry * 0.95

            outcomes[key] = {
                "key": key,
                "date": str(event.get("seen_at", ""))[:10],
                "timestamp": event.get("seen_at"),
                "symbol": event.get("symbol"),
                "entry": entry,
                "flash_drop_pct": drop,
                "miss_score": float(event.get("miss_score", 999)),
                "target": target,
                "stop": stop,
                "paper_notional": 1000.0,
                "status": "open",
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
        if rec.get("status") == "closed":
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

    for rec in outcomes.values():
        if rec.get("status") == "closed":
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
            exit_row = None
            reason = None

            for _, row in sdf.iterrows():
                px = float(row["price"])
                et = row["timestamp"].tz_convert(ZoneInfo("America/New_York"))
                if px >= target:
                    exit_row, reason = row, "target"
                    break
                if px <= stop:
                    exit_row, reason = row, "stop"
                    break
                if (et.hour, et.minute) >= (15, 55):
                    exit_row, reason = row, "end"
                    break

            if exit_row is None:
                continue

            exit_price = target if reason == "target" else stop if reason == "stop" else float(exit_row["price"])
            ret_pct = (exit_price / float(rec["entry"]) - 1) * 100
            rec.update({
                "status": "closed",
                "exit_time": str(exit_row["timestamp"]),
                "exit_price": exit_price,
                "exit_reason": reason,
                "ret_pct": ret_pct,
                "pnl_usd": float(rec.get("paper_notional", 1000.0)) * ret_pct / 100.0,
            })
        except Exception:
            pass

    save_near_miss_paper(outcomes)

    rows = sorted(outcomes.values(), key=lambda r: str(r.get("timestamp", "")), reverse=True)[:max_items]
    if not rows:
        return ["None"]

    lines = []
    for row in rows:
        if row.get("status") == "closed":
            lines.append(
                f"{row.get('timestamp')} | {row.get('symbol')} | "
                f"entry={float(row.get('entry', 0)):.2f} | "
                f"drop={float(row.get('flash_drop_pct', 0)):.2f}% | "
                f"target={float(row.get('target', 0)):.2f} | "
                f"stop={float(row.get('stop', 0)):.2f} | "
                f"exit={float(row.get('exit_price', 0)):.2f} | "
                f"reason={row.get('exit_reason')} | "
                f"return={float(row.get('ret_pct', 0)):+.2f}% | "
                f"P/L_on_$1000={float(row.get('pnl_usd', 0)):+.2f}"
            )
        else:
            lines.append(
                f"{row.get('timestamp')} | {row.get('symbol')} | "
                f"entry={float(row.get('entry', 0)):.2f} | "
                f"drop={float(row.get('flash_drop_pct', 0)):.2f}% | "
                f"target={float(row.get('target', 0)):.2f} | "
                f"stop={float(row.get('stop', 0)):.2f} | status=OPEN"
            )
    return lines

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
            signal_events_today = [e for e in today_events if e.get("event_type") == "SIGNAL"]
            trigger_events_today = [e for e in today_events if e.get("event_type") == "ENTRY_TRIGGER_OCO_ATTEMPT"]
            execution_events_today = [e for e in today_events if e.get("event_type") in ("BUY_ATTEMPT", "BUY_RESPONSE", "BUY_ERROR", "SELL_ATTEMPT", "SELL_RESPONSE", "SELL_ERROR")]

            top_today = []
            triggers_today = 0
            for r in today_rows:
                triggers_today = max(triggers_today, int(r.get("total_triggers_today", 0) or 0))
                for e in r.get("latest_nearest", []) or []:
                    x = dict(e)
                    x["seen_at"] = r.get("timestamp")
                    top_today.append(x)

            top_today = sorted(top_today, key=lambda e: float(e.get("miss_score", 999)))[:5]

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
                *token_health_lines(),
                "",
                *storage_health_lines(),
                "",
                "AUTH DOWNTIME / WARNING HISTORY TODAY",
                *auth_downtime_history_lines(),
                "",
                "ACTIVE THRESHOLDS",
                "flash_drop >= 2.00%",
                "pre_return >= 0.25%",
                "pre_slope >= 0.50%/hr",
                "max_flash_drop <= 12.00%",
                "",
                "LATEST NEAREST MISSES",
            ]

            if latest and latest.get("latest_nearest"):
                for e in latest["latest_nearest"][:5]:
                    lines.append(fmt_near(e))
            else:
                lines.append("None")

            lines += ["", "TOP 5 NEAREST MISSES TODAY"]
            if top_today:
                for e in top_today:
                    lines.append(f"{fmt_near(e)} | seen={e.get('seen_at')}")
            else:
                lines.append("None")

            lines += ["", "TOP 5 NEAR-MISS PAPER OUTCOMES — PAPER ONLY"]
            for line in near_miss_paper_lines(top_today, max_items=25):
                lines.append(line)

            lines += ["", "TRIGGERS TODAY"]
            if latest and latest.get("latest_triggers"):
                for e in latest["latest_triggers"][:10]:
                    lines.append(str(e))
            else:
                lines.append("None")
            lines.append(f"Total triggers today: {triggers_today}")

            lines += ["", "TRIGGER TRADE LEDGER TODAY"]
            if trigger_events_today:
                for e in trigger_events_today[-50:]:
                    lines.append(summarize_trigger_event(e))
            else:
                lines.append("None")

            lines += ["", "SIGNAL PAPER OUTCOMES"]
            for line in signal_paper_outcome_lines(
                [
                    e for e in events
                    if e.get("event_type") == "SIGNAL"
                    and is_rth_timestamp(e.get("timestamp"))
                ],
                max_items=100,
            ):
                lines.append(line)

            lines += ["", "FULL SIGNAL LEDGER TODAY"]
            if signal_events_today:
                for e in signal_events_today[-20:]:
                    lines.append(summarize_signal_event(e))
            else:
                lines.append("None")

            near_miss_events_today = [e for e in today_events if e.get("event_type") == "NEAR_MISS"]
            lines += ["", "NEAR MISS EVENTS TODAY"]
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
