#!/usr/bin/env python3

import argparse
import json
import math
import pickle
import re
import sys
from collections import Counter, defaultdict
from datetime import time
from pathlib import Path

import pandas as pd


DATA = Path("/data")
CACHE = DATA / "trading_analyzer_cache"
CACHE.mkdir(parents=True, exist_ok=True)

LEDGER = DATA / "paper_signal_outcomes.jsonl"


EVENT_FIELDS = [
    "event", "type", "event_type", "record_type",
    "kind", "action", "status",
]

TIME_FIELDS = [
    "entry_timestamp",
    "exit_timestamp",
    "signal_timestamp",
    "timestamp",
    "observed_at",
    "created_at",
    "time",
]

STRATEGY_FIELDS = [
    "strategy_id", "strategy", "module", "module_id",
    "strategy_name", "name",
]

ID_FIELDS = [
    "setup_id", "trade_id", "signal_id", "id",
]


def first_value(record, names):
    for name in names:
        if name in record and record[name] not in (None, ""):
            return record[name]
    return None


def number(value):
    try:
        x = float(value)
        if math.isfinite(x):
            return x
    except Exception:
        pass
    return None


def timestamp_from_record(record, prefer_exit=False):
    fields = TIME_FIELDS
    if prefer_exit:
        fields = [
            "exit_timestamp",
            "timestamp",
            "entry_timestamp",
            "signal_timestamp",
            "observed_at",
            "created_at",
            "time",
        ]

    for field in fields:
        if field not in record:
            continue
        try:
            ts = pd.to_datetime(record[field], utc=True, errors="coerce")
            if pd.notna(ts):
                return ts
        except Exception:
            pass
    return pd.NaT


def event_from_record(record):
    for key in EVENT_FIELDS:
        value = record.get(key)
        if value is not None:
            s = str(value).upper()
            if "PAPER_ENTRY" in s:
                return "PAPER_ENTRY"
            if "PAPER_EXIT" in s:
                return "PAPER_EXIT"
            if s == "ENTRY":
                return "PAPER_ENTRY"
            if s == "EXIT":
                return "PAPER_EXIT"

    # Fall back to searching string values.
    for value in record.values():
        if not isinstance(value, str):
            continue
        s = value.upper()
        if s == "PAPER_ENTRY":
            return "PAPER_ENTRY"
        if s == "PAPER_EXIT":
            return "PAPER_EXIT"

    return None


def strategy_field(record, strategy):
    for key in STRATEGY_FIELDS:
        if str(record.get(key, "")) == strategy:
            return key

    for key, value in record.items():
        if str(value) == strategy:
            return key

    return None


def setup_id(record):
    return first_value(record, ID_FIELDS)


def symbol(record):
    return first_value(record, ["symbol", "ticker"])


def ledger_cache_path(strategy):
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", strategy)
    return CACHE / f"ledger_{safe}.pkl"


def load_strategy_records(strategy, verbose=True):
    if not LEDGER.exists():
        raise FileNotFoundError(LEDGER)

    cache_path = ledger_cache_path(strategy)
    stat = LEDGER.stat()

    state = {
        "inode": stat.st_ino,
        "offset": 0,
        "records": [],
    }

    if cache_path.exists():
        try:
            with cache_path.open("rb") as f:
                old = pickle.load(f)

            if (
                old.get("inode") == stat.st_ino
                and old.get("offset", 0) <= stat.st_size
            ):
                state = old
                if verbose:
                    print(
                        f"[ledger cache] {len(state['records']):,} cached records; "
                        f"reading only appended bytes...",
                        flush=True,
                    )
        except Exception:
            pass

    if state["offset"] > stat.st_size:
        state = {
            "inode": stat.st_ino,
            "offset": 0,
            "records": [],
        }

    if state["offset"] == 0 and verbose:
        print("[ledger] first scan; building persistent strategy cache...", flush=True)

    needle = strategy

    with LEDGER.open("rb") as f:
        f.seek(state["offset"])

        while True:
            line = f.readline()
            if not line:
                break

            if needle.encode() not in line:
                continue

            try:
                rec = json.loads(line)
            except Exception:
                continue

            # Canonical strategy records only.
            # Do NOT include research/sweep descendants merely because
            # source_strategy_id points back to this strategy.
            if str(rec.get("strategy_id", "")) == strategy:
                state["records"].append(rec)

        state["offset"] = f.tell()
        state["inode"] = stat.st_ino

    tmp = cache_path.with_suffix(".tmp")
    with tmp.open("wb") as f:
        pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(cache_path)

    if verbose:
        print(
            f"[ledger] {len(state['records']):,} matching records available",
            flush=True,
        )

    return state["records"]


def show_schema(strategy):
    records = load_strategy_records(strategy)

    print("\n=== SCHEMA ===")
    if not records:
        print("No matching records found.")
        return

    keys = Counter()
    events = Counter()
    strategy_keys = Counter()

    for rec in records:
        keys.update(rec.keys())
        ev = event_from_record(rec)
        if ev:
            events[ev] += 1
        sf = strategy_field(rec, strategy)
        if sf:
            strategy_keys[sf] += 1

    print("\nStrategy fields:")
    for k, n in strategy_keys.most_common():
        print(f"  {k}: {n:,}")

    print("\nEvents:")
    for k, n in events.most_common():
        print(f"  {k}: {n:,}")

    print("\nMost common keys:")
    for k, n in keys.most_common(50):
        print(f"  {k}: {n:,}")

    print("\nFirst matching record:")
    for k in sorted(records[0]):
        print(f"  {k}: {records[0][k]}")


def normalized_rows(strategy):
    records = load_strategy_records(strategy)

    rows = []

    for rec in records:
        ev = event_from_record(rec)
        if ev not in ("PAPER_ENTRY", "PAPER_EXIT"):
            continue

        ts = timestamp_from_record(rec, prefer_exit=(ev == "PAPER_EXIT"))

        row = {
            "_event": ev,
            "_timestamp": ts,
            "_day": str(ts.date()) if pd.notna(ts) else None,
            "_setup_id": setup_id(rec),
            "_symbol": symbol(rec),
            "_raw": rec,
        }

        for key in [
            "entry_price",
            "target_price",
            "stop_price",
            "exit_price",
            "observed_price",
            "return_pct",
            "return_percent",
            "return",
        ]:
            if key in rec:
                row[key] = rec[key]

        rows.append(row)

    return rows


def pair_trades(strategy):
    rows = normalized_rows(strategy)

    entries = {}
    exits = []

    for row in rows:
        sid = row["_setup_id"]

        if row["_event"] == "PAPER_ENTRY":
            if sid is not None:
                entries[sid] = row
        else:
            exits.append(row)

    trades = []

    for ex in exits:
        sid = ex["_setup_id"]
        en = entries.get(sid)

        raw_e = en["_raw"] if en else {}
        raw_x = ex["_raw"]

        ets = en["_timestamp"] if en else pd.NaT
        xts = ex["_timestamp"]

        ret = first_value(
            raw_x,
            ["return_pct", "return_percent", "return", "pct_return"],
        )
        ret = number(ret)

        entry = number(first_value(
            raw_e or raw_x,
            ["entry_price", "entry", "price"],
        ))
        target = number(first_value(
            raw_e or raw_x,
            ["target_price", "target"],
        ))
        stop = number(first_value(
            raw_e or raw_x,
            ["stop_price", "stop"],
        ))
        exit_px = number(first_value(
            raw_x,
            ["exit_price", "observed_price", "price"],
        ))

        reason = first_value(
            raw_x,
            ["exit_reason", "reason", "outcome", "status"],
        )

        activated = first_value(
            raw_x,
            ["activated", "activation", "was_activated"],
        )
        if activated is None and raw_e:
            activated = first_value(
                raw_e,
                ["activated", "activation", "was_activated"],
            )

        hold_s = None
        if pd.notna(ets) and pd.notna(xts):
            try:
                hold_s = (xts - ets).total_seconds()
            except Exception:
                pass

        trade = {
            "day": str(ets.date()) if pd.notna(ets) else ex["_day"],
            "symbol": ex["_symbol"] or (en["_symbol"] if en else None),
            "setup_id": sid,
            "entry_ts": ets,
            "exit_ts": xts,
            "return_pct": ret,
            "entry_price": entry,
            "target_price": target,
            "stop_price": stop,
            "exit_price": exit_px,
            "exit_reason": str(reason) if reason is not None else None,
            "activated": activated,
            "hold_s": hold_s,
            "_entry_raw": raw_e,
            "_exit_raw": raw_x,
        }

        if entry:
            if target is not None:
                trade["target_distance_pct"] = (target / entry - 1) * 100
            if stop is not None:
                trade["stop_distance_pct"] = (stop / entry - 1) * 100
            if exit_px is not None:
                trade["realized_move_pct"] = (exit_px / entry - 1) * 100

        trades.append(trade)

    return trades


def boolish(value):
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("true", "1", "yes", "y"):
        return True
    if s in ("false", "0", "no", "n", "none"):
        return False
    return None


def summarize_day(trades, day):
    subset = [t for t in trades if t["day"] == day]

    returns = [t["return_pct"] for t in subset if t["return_pct"] is not None]

    stops = [
        t for t in subset
        if t["exit_reason"] and "STOP" in t["exit_reason"].upper()
    ]

    activated = [
        t for t in subset
        if boolish(t["activated"]) is True
    ]

    wins = [r for r in returns if r > 0]

    print(f"\n=== {day} ===")
    print(f"Trades:       {len(subset):,}")

    if returns:
        print(f"Sum return:   {sum(returns):+.3f}")
        print(f"Mean return:  {pd.Series(returns).mean():+.4f}%")
        print(f"Median:       {pd.Series(returns).median():+.4f}%")
        print(f"Win rate:     {100*len(wins)/len(returns):.1f}%")

    if subset:
        print(f"Stop rate:    {100*len(stops)/len(subset):.1f}%")

        known_act = [
            t for t in subset if boolish(t["activated"]) is not None
        ]
        if known_act:
            print(
                f"Activated:    "
                f"{100*len(activated)/len(known_act):.1f}%"
            )

    holds = [
        t["hold_s"] for t in subset
        if t["hold_s"] is not None and t["hold_s"] >= 0
    ]
    if holds:
        print(f"Median hold:  {pd.Series(holds).median():.1f}s")

    symbols = [t["symbol"] for t in subset if t["symbol"]]
    if symbols:
        counts = Counter(symbols)
        repeats = sum(v - 1 for v in counts.values() if v > 1)
        print(f"Symbols:      {len(counts):,}")
        print(f"Repeat trades:{repeats:,.0f}")


def numeric_entry_features(trades, day):
    values = defaultdict(list)
    for trade in trades:
        if trade["day"] != day:
            continue
        rec = trade["_entry_raw"]
        for key, value in rec.items():
            if isinstance(value, bool):
                continue
            x = number(value)
            if x is None:
                continue
            kl = key.lower()
            if any(s in kl for s in [
                "timestamp", "time_ms", "_id", "notional"
            ]):
                continue
            values[key].append(x)
    return values


def compare_features(trades, day1, day2):
    f1 = numeric_entry_features(trades, day1)
    f2 = numeric_entry_features(trades, day2)
    candidates = []
    for key in set(f1) & set(f2):
        a = pd.Series(f1[key], dtype=float)
        b = pd.Series(f2[key], dtype=float)
        if len(a) < 10 or len(b) < 10:
            continue
        med1 = a.median()
        med2 = b.median()
        combined = pd.concat([a, b])
        scale = combined.quantile(.75) - combined.quantile(.25)
        if not scale or not math.isfinite(scale):
            scale = combined.std()
        if not scale or not math.isfinite(scale):
            continue
        shift = abs(med2 - med1) / scale
        candidates.append((shift, key, len(a), med1, len(b), med2))
    candidates.sort(reverse=True)
    print("\n=== BIGGEST ENTRY-FEATURE SHIFTS ===")
    print(
        f"{'FEATURE':32s} {'N1':>6s} {'MED1':>12s} "
        f"{'N2':>6s} {'MED2':>12s} {'SHIFT':>8s}"
    )
    for shift, key, n1, m1, n2, m2 in candidates[:25]:
        print(
            f"{key[:32]:32s} {n1:6d} {m1:12.5g} "
            f"{n2:6d} {m2:12.5g} {shift:8.3f}"
        )


def hourly(trades, day):
    buckets = defaultdict(list)
    for t in trades:
        if t["day"] != day:
            continue
        if pd.isna(t["entry_ts"]):
            continue
        if t["return_pct"] is None:
            continue
        buckets[t["entry_ts"].hour].append(t["return_pct"])
    print(f"\n=== HOURLY UTC: {day} ===")
    print("HOUR    N      SUM       AVG     WIN%")
    for hour in sorted(buckets):
        rs = buckets[hour]
        wins = sum(1 for r in rs if r > 0)
        print(
            f"{hour:02d}:00 {len(rs):5d} "
            f"{sum(rs):+9.3f} "
            f"{pd.Series(rs).mean():+8.4f} "
            f"{100*wins/len(rs):6.1f}"
        )


def compare(strategy, day1, day2):
    print(f"=== TRADE COMPARISON: {strategy} ===")
    trades = pair_trades(strategy)
    print(f"[paired trades] {len(trades):,}", flush=True)
    summarize_day(trades, day1)
    summarize_day(trades, day2)
    hourly(trades, day1)
    hourly(trades, day2)
    compare_features(trades, day1, day2)


def feed_cache_path(day):
    return CACHE / f"feed_{day}.pkl"


def feed_summary(day):
    compact = day.replace("-", "")
    path = DATA / "research_market" / f"minute_market_quotes_{compact}.csv.gz"
    if not path.exists():
        return {"day": day, "error": "MISSING"}
    cache_path = feed_cache_path(compact)
    stat = path.stat()
    if cache_path.exists():
        try:
            with cache_path.open("rb") as f:
                cached = pickle.load(f)
            if (
                cached.get("_size") == stat.st_size
                and cached.get("_mtime") == stat.st_mtime_ns
            ):
                cached["_cached"] = True
                return cached
        except Exception:
            pass
    print(f"[feed {day}] scanning two columns only...", flush=True)
    rows = 0
    symbols = set()
    first = None
    last = None
    per_minute = Counter()
    usecols = ["market_minute_utc", "symbol"]
    for chunk_no, df in enumerate(
        pd.read_csv(path, usecols=usecols, chunksize=250_000), 1
    ):
        rows += len(df)
        ts = pd.to_datetime(df["market_minute_utc"], utc=True, errors="coerce")
        good = ts.notna() & df["symbol"].notna()
        ts = ts[good].dt.floor("min")
        sy = df.loc[good, "symbol"].astype(str)
        if len(ts):
            mn = ts.min()
            mx = ts.max()
            first = mn if first is None else min(first, mn)
            last = mx if last is None else max(last, mx)
            symbols.update(sy.unique())
            vc = ts.value_counts()
            for minute, count in vc.items():
                per_minute[minute] += int(count)
        print(f"  chunk {chunk_no}: {rows:,} rows", flush=True)
    counts = list(per_minute.values())
    result = {
        "day": day,
        "rows": rows,
        "symbols": len(symbols),
        "minutes": len(per_minute),
        "first": first,
        "last": last,
        "median_rows_per_minute": (
            float(pd.Series(counts).median()) if counts else None
        ),
        "p10_rows_per_minute": (
            float(pd.Series(counts).quantile(.10)) if counts else None
        ),
        "_size": stat.st_size,
        "_mtime": stat.st_mtime_ns,
        "_cached": False,
    }
    with cache_path.open("wb") as f:
        pickle.dump(result, f, protocol=pickle.HIGHEST_PROTOCOL)
    return result


def show_feed(days):
    print("=== FEED HEALTH ===")
    results = [feed_summary(d) for d in days]
    print(
        "\nDAY          ROWS     SYMS  MINUTES "
        "MED/MIN  P10/MIN  FIRST                     LAST"
    )
    for r in results:
        if "error" in r:
            print(f"{r['day']} {r['error']}")
            continue
        cache_mark = "*" if r.get("_cached") else " "
        print(
            f"{r['day']} "
            f"{r['rows']:10,d} "
            f"{r['symbols']:7,d} "
            f"{r['minutes']:8,d} "
            f"{r['median_rows_per_minute']:8.1f} "
            f"{r['p10_rows_per_minute']:8.1f} "
            f"{str(r['first']):25s} "
            f"{str(r['last']):25s}"
            f"{cache_mark}"
        )
    print("\n* = loaded from cache")


# ---------- Curve / regime feature engine ----------

PRICE_PREFERENCE = ["mark", "last", "legacy_price"]


def market_path(day):
    compact = day.replace("-", "")
    return DATA / "research_market" / f"minute_market_quotes_{compact}.csv.gz"


def feature_cache_path(strategy, day):
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", strategy)
    compact = day.replace("-", "")
    return CACHE / f"features_{safe}_{compact}_v3.pkl"


def _choose_market_columns(path):
    header = pd.read_csv(path, nrows=0).columns.tolist()
    cols = ["market_minute_utc", "symbol"]
    for name in PRICE_PREFERENCE + ["bid", "ask"]:
        if name in header and name not in cols:
            cols.append(name)
    return cols


def _make_price_column(df):
    px = pd.Series(index=df.index, dtype=float)
    for name in PRICE_PREFERENCE:
        if name in df.columns:
            candidate = pd.to_numeric(df[name], errors="coerce")
            px = px.combine_first(candidate)
    if "bid" in df.columns and "ask" in df.columns:
        bid = pd.to_numeric(df["bid"], errors="coerce")
        ask = pd.to_numeric(df["ask"], errors="coerce")
        mid = (bid + ask) / 2.0
        valid_mid = (bid > 0) & (ask > 0) & (ask >= bid)
        px = px.combine_first(mid.where(valid_mid))
    return px


def load_market_frame(day):
    path = market_path(day)
    if not path.exists():
        raise FileNotFoundError(path)
    cols = _choose_market_columns(path)
    print(
        f"[features {day}] loading minute market ({', '.join(cols)})...",
        flush=True,
    )
    df = pd.read_csv(path, usecols=cols)
    df["_minute"] = pd.to_datetime(
        df["market_minute_utc"], utc=True, errors="coerce"
    ).dt.floor("min")
    df["_symbol"] = df["symbol"].astype(str)
    df["_price"] = _make_price_column(df)
    df = df[
        df["_minute"].notna()
        & df["_symbol"].notna()
        & df["_price"].notna()
        & (df["_price"] > 0)
    ][["_minute", "_symbol", "_price"]]
    df = (
        df.sort_values(["_symbol", "_minute"])
        .groupby(["_symbol", "_minute"], as_index=False)
        .last()
    )
    print(
        f"[features {day}] {len(df):,} symbol-minutes, "
        f"{df['_symbol'].nunique():,} symbols",
        flush=True,
    )
    return df


def _asof_value(minutes, values, when):
    import bisect
    pos = bisect.bisect_right(minutes, when.value) - 1
    if pos < 0:
        return None
    return float(values[pos])


def _window_values(minutes, values, start, end):
    import bisect
    lo = bisect.bisect_left(minutes, start.value)
    hi = bisect.bisect_right(minutes, end.value)
    if hi <= lo:
        return []
    return [float(x) for x in values[lo:hi]]


def _pct(a, b):
    if a is None or b is None or b <= 0:
        return None
    return (a / b - 1.0) * 100.0


def _fresh_low_count(vals):
    if len(vals) < 2:
        return 0
    lows = 0
    running = vals[0]
    for x in vals[1:]:
        if x < running:
            lows += 1
            running = x
    return lows


def _safe_std_returns(vals):
    if len(vals) < 3:
        return None
    s = pd.Series(vals, dtype=float).pct_change().dropna() * 100.0
    if len(s) < 2:
        return None
    return float(s.std())


def _market_context(frame):
    wide = frame.pivot(
        index="_minute",
        columns="_symbol",
        values="_price",
    ).sort_index()

    r1 = wide.pct_change(1, fill_method=None) * 100.0
    r5 = wide.pct_change(5, fill_method=None) * 100.0

    out = pd.DataFrame(index=wide.index)

    valid1 = r1.notna().sum(axis=1)
    valid5 = r5.notna().sum(axis=1)

    out["breadth_down_1m"] = (
        (r1 < 0).sum(axis=1) / valid1.where(valid1 > 0)
    )
    out["breadth_down_5m"] = (
        (r5 < 0).sum(axis=1) / valid5.where(valid5 > 0)
    )
    out["cross_median_ret_1m"] = r1.median(axis=1, skipna=True)
    out["cross_median_ret_5m"] = r5.median(axis=1, skipna=True)
    out["cross_p10_ret_1m"] = r1.quantile(.10, axis=1)
    out["cross_p10_ret_5m"] = r5.quantile(.10, axis=1)

    return out


def build_day_features(strategy, trades, day, force=False):
    subset = [
        t for t in trades
        if t["day"] == day
        and pd.notna(t["entry_ts"])
        and t["symbol"]
        and t["return_pct"] is not None
    ]

    if not subset:
        return pd.DataFrame()

    path = market_path(day)
    if not path.exists():
        print(f"[features {day}] market file missing: {path}", flush=True)
        return pd.DataFrame()

    cache_path = feature_cache_path(strategy, day)
    stat = path.stat()
    ledger_stat = LEDGER.stat()

    if cache_path.exists() and not force:
        try:
            with cache_path.open("rb") as f:
                cached = pickle.load(f)
            meta = cached.get("meta", {})
            if (
                meta.get("market_size") == stat.st_size
                and meta.get("market_mtime") == stat.st_mtime_ns
                and meta.get("ledger_size") == ledger_stat.st_size
            ):
                print(
                    f"[features {day}] cache hit: "
                    f"{len(cached['frame']):,} trades",
                    flush=True,
                )
                return cached["frame"]
        except Exception:
            pass

    frame = load_market_frame(day)
    context = _market_context(frame)

    by_symbol = {}
    for sym, g in frame.groupby("_symbol", sort=False):
        g = g.sort_values("_minute")
        # Normalize explicitly to nanoseconds.  Do not rely on
        # astype("int64") because pandas datetime resolution can be us/ns
        # depending on the input/build, while Timestamp.value is always ns.
        minute_ns = g["_minute"].map(lambda x: int(x.value)).to_numpy(dtype="int64")
        by_symbol[sym] = (
            minute_ns,
            g["_price"].to_numpy(dtype=float),
        )

    all_entry_ns = sorted(int(t["entry_ts"].value) for t in subset)

    by_symbol_entry_ns = defaultdict(list)
    for t in subset:
        by_symbol_entry_ns[t["symbol"]].append(int(t["entry_ts"].value))

    for sym in by_symbol_entry_ns:
        by_symbol_entry_ns[sym].sort()

    import bisect

    rows = []

    for i, t in enumerate(
        sorted(subset, key=lambda x: x["entry_ts"]),
        1,
    ):
        ets = t["entry_ts"]

        # Anti-lookahead rule:
        # exclude the entry minute itself from ALL candidate features.
        cutoff = ets.floor("min") - pd.Timedelta(minutes=1)

        sym = t["symbol"]

        rec = {
            "day": day,
            "setup_id": t["setup_id"],
            "symbol": sym,
            "entry_ts": ets,
            "entry_price": t["entry_price"],
            "return_pct": t["return_pct"],
            "exit_reason": t["exit_reason"],
            "activated": boolish(t["activated"]),
            "hold_s": t["hold_s"],
        }

        arr = by_symbol.get(sym)

        if arr:
            mins_ns, vals = arr

            p0 = _asof_value(mins_ns, vals, cutoff)
            rec["pre_px"] = p0

            for k in (1, 2, 3, 5, 10):
                pk = _asof_value(
                    mins_ns,
                    vals,
                    cutoff - pd.Timedelta(minutes=k),
                )
                rec[f"ret_{k}m"] = _pct(p0, pk)

                if rec[f"ret_{k}m"] is not None:
                    rec[f"slope_{k}m"] = rec[f"ret_{k}m"] / k

            p1 = _asof_value(
                mins_ns,
                vals,
                cutoff - pd.Timedelta(minutes=1),
            )

            p2 = _asof_value(
                mins_ns,
                vals,
                cutoff - pd.Timedelta(minutes=2),
            )

            r_last = _pct(p0, p1)
            r_prev = _pct(p1, p2)

            rec["accel_2m"] = (
                r_last - r_prev
                if r_last is not None and r_prev is not None
                else None
            )

            for k in (3, 5, 10):
                vals_k = _window_values(
                    mins_ns,
                    vals,
                    cutoff - pd.Timedelta(minutes=k - 1),
                    cutoff,
                )

                if vals_k and p0 is not None:
                    rec[f"dist_from_{k}m_high"] = _pct(
                        p0,
                        max(vals_k),
                    )

                    rec[f"dist_from_{k}m_low"] = _pct(
                        p0,
                        min(vals_k),
                    )

                    rec[f"fresh_lows_{k}m"] = _fresh_low_count(vals_k)

                    rec[f"vol_{k}m"] = _safe_std_returns(vals_k)

                    rec[f"obs_{k}m"] = len(vals_k)

            # Diagnostic only. These are future measurements and are
            # explicitly excluded from filter discovery.
            entry_px = t["entry_price"]

            for k in (1, 2, 5):
                future_t = (
                    ets.floor("min")
                    + pd.Timedelta(minutes=k)
                )

                fp = _asof_value(
                    mins_ns,
                    vals,
                    future_t,
                )

                rec[f"fwd_{k}m_from_entry"] = _pct(
                    fp,
                    entry_px,
                )

        if cutoff in context.index:
            crow = context.loc[cutoff]

            for name in context.columns:
                value = crow[name]

                rec[name] = (
                    float(value)
                    if pd.notna(value)
                    else None
                )

        now_ns = int(ets.value)

        rec["signal_density_1m"] = (
            bisect.bisect_right(all_entry_ns, now_ns)
            - bisect.bisect_left(
                all_entry_ns,
                now_ns - int(60 * 1e9),
            )
        )

        rec["signal_density_5m"] = (
            bisect.bisect_right(all_entry_ns, now_ns)
            - bisect.bisect_left(
                all_entry_ns,
                now_ns - int(300 * 1e9),
            )
        )

        same = by_symbol_entry_ns[sym]

        rec["same_symbol_density_5m"] = (
            bisect.bisect_right(same, now_ns)
            - bisect.bisect_left(
                same,
                now_ns - int(300 * 1e9),
            )
        )

        rec["utc_hour"] = (
            ets.hour
            + ets.minute / 60.0
        )

        rows.append(rec)

        if i % 100 == 0 or i == len(subset):
            print(
                f"[features {day}] "
                f"{i:,}/{len(subset):,} trades",
                flush=True,
            )

    out = pd.DataFrame(rows)

    payload = {
        "meta": {
            "market_size": stat.st_size,
            "market_mtime": stat.st_mtime_ns,
            "ledger_size": ledger_stat.st_size,
            "version": 3,
        },
        "frame": out,
    }

    with cache_path.open("wb") as f:
        pickle.dump(
            payload,
            f,
            protocol=pickle.HIGHEST_PROTOCOL,
        )

    return out


NON_FILTER_COLUMNS = {
    "return_pct",
    "entry_price",
    "pre_px",
    "hold_s",
    "fwd_1m_from_entry",
    "fwd_2m_from_entry",
    "fwd_5m_from_entry",
    "utc_hour",
}


def candidate_feature_columns(df):
    cols = []

    for col in df.columns:
        if col in NON_FILTER_COLUMNS:
            continue

        if col in {
            "day",
            "setup_id",
            "symbol",
            "entry_ts",
            "exit_reason",
            "activated",
        }:
            continue

        s = pd.to_numeric(
            df[col],
            errors="coerce",
        )

        if (
            s.notna().sum() >= 50
            and s.nunique(dropna=True) >= 5
        ):
            cols.append(col)

    return cols


def show_feature_comparison(
    strategy,
    days,
    force=False,
):
    trades = pair_trades(strategy)

    frames = [
        build_day_features(
            strategy,
            trades,
            d,
            force=force,
        )
        for d in days
    ]

    frames = [
        x for x in frames
        if not x.empty
    ]

    if not frames:
        print("No feature rows available.")
        return

    df = pd.concat(
        frames,
        ignore_index=True,
    )

    print("\n=== CURVE / REGIME FEATURES ===")

    print(
        f"Rows: {len(df):,} | "
        f"Days: {df['day'].nunique()} | "
        f"Candidate pre-entry features: "
        f"{len(candidate_feature_columns(df))}"
    )

    for day in sorted(df["day"].unique()):
        d = df[df["day"] == day]

        stop_rate = (
            d["exit_reason"]
            .fillna("")
            .str.upper()
            .str.contains("STOP")
            .mean()
        )

        act_rate = (
            d["activated"]
            .fillna(False)
            .astype(bool)
            .mean()
        )

        print(
            f"{day}: "
            f"N={len(d):4d} "
            f"avg={d['return_pct'].mean():+.4f}% "
            f"stop={100*stop_rate:5.1f}% "
            f"act={100*act_rate:5.1f}%"
        )

    if len(days) == 2:
        a = df[df["day"] == days[0]]
        b = df[df["day"] == days[1]]

        shifts = []

        for col in candidate_feature_columns(df):
            x = pd.to_numeric(
                a[col],
                errors="coerce",
            ).dropna()

            y = pd.to_numeric(
                b[col],
                errors="coerce",
            ).dropna()

            if len(x) < 20 or len(y) < 20:
                continue

            combined = pd.concat([x, y])

            scale = (
                combined.quantile(.75)
                - combined.quantile(.25)
            )

            if (
                not scale
                or not math.isfinite(scale)
            ):
                continue

            shifts.append(
                (
                    abs(y.median() - x.median()) / scale,
                    col,
                    len(x),
                    x.median(),
                    len(y),
                    y.median(),
                )
            )

        shifts.sort(reverse=True)

        print("\n=== PRE-ENTRY FEATURE SHIFTS ===")

        print(
            f"{'FEATURE':28s} "
            f"{'N1':>5s} "
            f"{'MED1':>10s} "
            f"{'N2':>5s} "
            f"{'MED2':>10s} "
            f"{'SHIFT':>7s}"
        )

        for (
            shift,
            col,
            n1,
            m1,
            n2,
            m2,
        ) in shifts[:30]:

            print(
                f"{col[:28]:28s} "
                f"{n1:5d} "
                f"{m1:10.4f} "
                f"{n2:5d} "
                f"{m2:10.4f} "
                f"{shift:7.3f}"
            )


def _metrics(df):
    if df.empty:
        return None

    ret = pd.to_numeric(
        df["return_pct"],
        errors="coerce",
    ).dropna()

    if ret.empty:
        return None

    stop = (
        df["exit_reason"]
        .fillna("")
        .str.upper()
        .str.contains("STOP")
    )

    act = (
        df["activated"]
        .fillna(False)
        .astype(bool)
    )

    daily = (
        df.assign(
            _ret=pd.to_numeric(
                df["return_pct"],
                errors="coerce",
            )
        )
        .groupby("day")["_ret"]
        .sum()
    )

    return {
        "n": len(df),
        "mean": float(ret.mean()),
        "sum": float(ret.sum()),
        "win": float((ret > 0).mean()),
        "stop": float(stop.mean()),
        "act": float(act.mean()),
        "worst_day": (
            float(daily.min())
            if len(daily)
            else float("nan")
        ),
    }


def _apply_filter(
    df,
    feature,
    op,
    threshold,
):
    s = pd.to_numeric(
        df[feature],
        errors="coerce",
    )

    if op == "<=":
        mask = s <= threshold
    else:
        mask = s >= threshold

    return df[mask.fillna(False)]


def discover_filters(
    strategy,
    days,
    force=False,
    topn=25,
):
    days = sorted(
        dict.fromkeys(days)
    )

    trades = pair_trades(strategy)

    frames = [
        build_day_features(
            strategy,
            trades,
            d,
            force=force,
        )
        for d in days
    ]

    frames = [
        x for x in frames
        if not x.empty
    ]

    if len(frames) < 2:
        print(
            "Need at least two days "
            "with feature data."
        )
        return

    df = pd.concat(
        frames,
        ignore_index=True,
    )

    available_days = sorted(
        df["day"].unique()
    )

    split = max(
        1,
        int(
            math.ceil(
                len(available_days) * 0.6
            )
        ),
    )

    if split >= len(available_days):
        split = len(available_days) - 1

    train_days = available_days[:split]
    test_days = available_days[split:]

    train = df[
        df["day"].isin(train_days)
    ].copy()

    test = df[
        df["day"].isin(test_days)
    ].copy()

    base_train = _metrics(train)
    base_test = _metrics(test)

    print(
        "\n=== FILTER DISCOVERY "
        "(DAY-LEVEL OOS SPLIT) ==="
    )

    print(
        "TRAIN:",
        ", ".join(train_days),
    )

    print(
        "TEST: ",
        ", ".join(test_days),
    )

    print(
        f"BASE TRAIN "
        f"N={base_train['n']:,} "
        f"avg={base_train['mean']:+.4f}% "
        f"worst_day="
        f"{base_train['worst_day']:+.3f}"
    )

    print(
        f"BASE TEST  "
        f"N={base_test['n']:,} "
        f"avg={base_test['mean']:+.4f}% "
        f"worst_day="
        f"{base_test['worst_day']:+.3f}"
    )

    candidates = []

    for feature in candidate_feature_columns(train):
        s = pd.to_numeric(
            train[feature],
            errors="coerce",
        ).dropna()

        if len(s) < 100:
            continue

        thresholds = sorted(
            set(
                float(s.quantile(q))
                for q in (
                    .10,
                    .20,
                    .30,
                    .40,
                    .50,
                    .60,
                    .70,
                    .80,
                    .90,
                )
            )
        )

        for threshold in thresholds:
            for op in ("<=", ">="):
                kept = _apply_filter(
                    train,
                    feature,
                    op,
                    threshold,
                )

                keep_frac = (
                    len(kept)
                    / len(train)
                )

                if (
                    keep_frac < .30
                    or keep_frac > .95
                    or len(kept) < 75
                ):
                    continue

                m = _metrics(kept)

                if not m:
                    continue

                improvement = (
                    m["mean"]
                    - base_train["mean"]
                )

                candidates.append(
                    (
                        improvement,
                        feature,
                        op,
                        threshold,
                        keep_frac,
                        m,
                    )
                )

    candidates.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    selected = []
    seen = set()

    for item in candidates:
        _, feature, op, _, _, _ = item
        key = (feature, op)

        if key in seen:
            continue

        seen.add(key)
        selected.append(item)

        if len(selected) >= topn:
            break

    print(
        "\nTop filters selected "
        "on TRAIN only:"
    )

    print(
        f"{'FEATURE':24s} "
        f"{'OP':>2s} "
        f"{'THRESH':>9s} "
        f"{'KEEP':>6s} "
        f"{'TR_AVG':>8s} "
        f"{'TE_AVG':>8s} "
        f"{'TE_KEEP':>7s} "
        f"{'TE_WORST':>9s} "
        f"{'OOS':>5s}"
    )

    survivors = []

    for (
        _,
        feature,
        op,
        threshold,
        keep_frac,
        trm,
    ) in selected:

        test_kept = _apply_filter(
            test,
            feature,
            op,
            threshold,
        )

        tem = _metrics(test_kept)

        if not tem:
            continue

        test_keep = (
            len(test_kept)
            / len(test)
            if len(test)
            else 0
        )

        survives = (
            tem["mean"] > base_test["mean"]
            and tem["worst_day"]
            >= base_test["worst_day"]
        )

        print(
            f"{feature[:24]:24s} "
            f"{op:>2s} "
            f"{threshold:9.4f} "
            f"{100*keep_frac:5.1f}% "
            f"{trm['mean']:+8.4f} "
            f"{tem['mean']:+8.4f} "
            f"{100*test_keep:6.1f}% "
            f"{tem['worst_day']:+9.3f} "
            f"{'YES' if survives else 'no':>5s}"
        )

        if survives:
            survivors.append(
                (
                    feature,
                    op,
                    threshold,
                    trm,
                    tem,
                )
            )

    print(
        f"\nOOS survivors: "
        f"{len(survivors)}"
    )

    if survivors:
        print(
            "These are candidates for "
            "deeper walk-forward/submodule testing, "
            "not deployment."
        )


def main():
    parser = argparse.ArgumentParser(
        description="Fast trading-system forensic analyzer"
    )

    parser.add_argument(
        "--strategy",
        default="C3N25S10",
        help="Strategy/module identifier",
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    sub.add_parser("schema")

    p_compare = sub.add_parser("compare")
    p_compare.add_argument("day1")
    p_compare.add_argument("day2")

    p_day = sub.add_parser("day")
    p_day.add_argument("day")

    p_feed = sub.add_parser("feed")
    p_feed.add_argument("days", nargs="+")

    p_all = sub.add_parser("all")
    p_all.add_argument("day1")
    p_all.add_argument("day2")

    p_features = sub.add_parser("features")
    p_features.add_argument("days", nargs="+")
    p_features.add_argument(
        "--force",
        action="store_true",
    )

    p_discover = sub.add_parser("discover")
    p_discover.add_argument(
        "days",
        nargs="+",
    )
    p_discover.add_argument(
        "--force",
        action="store_true",
    )
    p_discover.add_argument(
        "--top",
        type=int,
        default=25,
    )

    args = parser.parse_args()

    if args.command == "schema":
        show_schema(args.strategy)

    elif args.command == "compare":
        compare(
            args.strategy,
            args.day1,
            args.day2,
        )

    elif args.command == "day":
        trades = pair_trades(args.strategy)
        summarize_day(
            trades,
            args.day,
        )
        hourly(
            trades,
            args.day,
        )

    elif args.command == "feed":
        show_feed(args.days)

    elif args.command == "all":
        compare(
            args.strategy,
            args.day1,
            args.day2,
        )
        print()
        show_feed(
            [
                args.day1,
                args.day2,
            ]
        )

    elif args.command == "features":
        show_feature_comparison(
            args.strategy,
            args.days,
            force=args.force,
        )

    elif args.command == "discover":
        discover_filters(
            args.strategy,
            args.days,
            force=args.force,
            topn=args.top,
        )


if __name__ == "__main__":
    main()
