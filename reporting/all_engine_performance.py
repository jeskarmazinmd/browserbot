"""Read-only, all-engine paper-performance snapshots.

The main signal ledger uses the existing risk-sized simulator.  Newer research
engines use five reusable $1,000 slots, matching the live-deployment convention
in :mod:`reporting.engine`.  Open positions are marked without mutating any
tracker state.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time as dt_time, timezone
import csv
import glob
import gzip
import heapq
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from reporting.capital_performance import simulate_day


NY = ZoneInfo("America/New_York")
STARTING_CASH = 5000.0
SLOTS = 5
EXIT_COMMISSION = 2.25


def parse_time(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def opened_time(row):
    for key in ("opened_at", "signal_timestamp", "timestamp", "recorded_at", "entry_timestamp"):
        value = parse_time(row.get(key))
        if value is not None:
            return value
    return None


def market_day(row):
    value = opened_time(row)
    return value.astimezone(NY).date().isoformat() if value else None


def cutoff_for(day: str, hour=16, minute=0):
    local = datetime.combine(date.fromisoformat(day), dt_time(hour, minute), NY)
    return local.astimezone(timezone.utc)


def strategy_name(row):
    return str(
        row.get("strategy_id") or row.get("strategy") or
        row.get("module_id") or row.get("module") or ""
    )


def row_id(row):
    return str(
        row.get("setup_id") or row.get("group_id") or
        row.get("event_id") or row.get("key") or ""
    )


def read_json_lines(path: Path):
    try:
        with path.open(errors="replace") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


def _snapshot_time(row):
    for key in ("timestamp", "recorded_at", "updated_at"):
        value = parse_time(row.get(key))
        if value:
            return value
    return None


def last_gzip_json(path: Path, cutoff=None):
    result = None
    try:
        with gzip.open(path, "rt", errors="replace") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (TypeError, ValueError):
                    continue
                timestamp = _snapshot_time(row)
                if cutoff is not None and timestamp is not None and timestamp > cutoff:
                    continue
                result = row
    except OSError:
        pass
    return result or {}


def all_gzip_json(path: Path, cutoff=None):
    try:
        with gzip.open(path, "rt", errors="replace") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (TypeError, ValueError):
                    continue
                timestamp = _snapshot_time(row)
                if cutoff is not None and timestamp is not None and timestamp > cutoff:
                    continue
                yield row
    except OSError:
        return


def latest_path(pattern):
    paths = sorted(Path(item) for item in glob.glob(str(pattern)))
    return paths[-1] if paths else None


def load_market_marks(root: Path, day: str, cutoff):
    compact = day.replace("-", "")
    equity = {}

    for pattern, field in (
        (root / "crosssection_tapes" / f"crosssection_quotes_{compact}.jsonl.gz", "quotes"),
        (root / "statarb_tapes" / f"statarb_quotes_{compact}.jsonl.gz", "quotes"),
        (root / "short_tapes" / f"short_quotes_{compact}.jsonl.gz", "quotes"),
    ):
        path = latest_path(pattern)
        if path:
            equity.update(last_gzip_json(path, cutoff).get(field, {}))

    main_last = {}
    main_tape = root / "tapes" / f"quotes_{compact}.csv"
    try:
        with main_tape.open(newline="") as handle:
            for row in csv.DictReader(handle):
                timestamp = parse_time(row.get("timestamp_utc"))
                if timestamp is not None and timestamp > cutoff:
                    continue
                try:
                    main_last[row["symbol"]] = float(row["last_price"])
                except (KeyError, TypeError, ValueError):
                    pass
    except OSError:
        pass

    options = {}
    path = latest_path(root / "options_tapes" / f"option_chains_{compact}.jsonl.gz")
    if path:
        for snapshot in all_gzip_json(path, cutoff):
            for contract in snapshot.get("contracts", []):
                symbol = contract.get("symbol")
                if symbol:
                    options[symbol] = contract

    futures = {}
    path = latest_path(root / "futures_tapes" / f"futures_quotes_{compact}.jsonl.gz")
    if path:
        futures.update(last_gzip_json(path, cutoff).get("exact", {}))

    curves = {}
    path = latest_path(root / "futures_curve_tapes" / f"curve_quotes_{compact}.jsonl.gz")
    if path:
        for contracts in last_gzip_json(path, cutoff).get("curves", {}).values():
            for contract in contracts:
                symbol = contract.get("symbol")
                if symbol:
                    curves[symbol] = contract

    forex = {}
    path = latest_path(root / "forex_tapes" / f"forex_quotes_{compact}.jsonl.gz")
    if path:
        forex.update(last_gzip_json(path, cutoff).get("pairs", {}))

    return {
        "equity": equity,
        "main_last": main_last,
        "options": options,
        "futures": futures,
        "curves": curves,
        "forex": forex,
    }


def equity_quote(symbol, marks):
    quote = marks["equity"].get(symbol)
    if quote:
        try:
            bid, ask = float(quote["bid"]), float(quote["ask"])
            if bid > 0 and ask > 0:
                return {"bid": bid, "ask": ask, "source": "bid_ask"}
        except (KeyError, TypeError, ValueError):
            pass
    try:
        value = float(marks["main_last"].get(symbol))
        if value > 0:
            return {"bid": value, "ask": value, "source": "main_last_fallback"}
    except (TypeError, ValueError):
        pass
    return {}


def close_equity(row, marks):
    quote = equity_quote(row.get("symbol"), marks)
    side = str(row.get("side", "")).upper()
    try:
        entry, shares = float(row["entry_price"]), float(row["shares"])
        exit_price = float(quote["bid"] if side == "LONG" else quote["ask"])
    except (KeyError, TypeError, ValueError):
        return None
    if side not in {"LONG", "SHORT"}:
        return None
    return (1.0 if side == "LONG" else -1.0) * (exit_price - entry) * shares


def close_equity_legs(row, marks):
    total = 0.0
    for leg in row.get("legs", []):
        quote = equity_quote(leg.get("symbol"), marks)
        side = str(leg.get("side", "")).upper()
        try:
            entry = float(leg["entry_price"])
            exit_price = float(quote["bid"] if side == "LONG" else quote["ask"])
        except (KeyError, TypeError, ValueError):
            return None
        if side not in {"LONG", "SHORT"}:
            return None
        sign = 1.0 if side == "LONG" else -1.0
        if leg.get("shares") is not None:
            total += sign * (exit_price - entry) * float(leg["shares"])
        elif leg.get("notional") is not None:
            total += float(leg["notional"]) * sign * (exit_price / entry - 1.0)
        else:
            return None
    return total


def close_futures(row, quote_map):
    total = 0.0
    for leg in row.get("legs", []):
        quote = quote_map.get(leg.get("symbol"), {})
        side = str(leg.get("side", "")).upper()
        try:
            entry = float(leg["entry_price"])
            multiplier = float(leg["multiplier"])
            commission = float(leg.get("entry_commission") or 0)
            close = float(quote["bid"] if side == "LONG" else quote["ask"])
        except (KeyError, TypeError, ValueError):
            return None
        gross = (close - entry) * multiplier if side == "LONG" else (entry - close) * multiplier
        total += gross - commission - EXIT_COMMISSION
    return total


def close_forex(row, quotes):
    total = 0.0
    for leg in row.get("legs", []):
        symbol = str(leg.get("symbol") or "")
        quote = quotes.get(symbol, {})
        side = str(leg.get("side", "")).upper()
        try:
            entry, units = float(leg["entry_price"]), int(leg["units"])
            close = float(quote["bid"] if side == "LONG" else quote["ask"])
        except (KeyError, TypeError, ValueError):
            return None
        pnl = (close - entry) * units * (1 if side == "LONG" else -1)
        if symbol.endswith("/USD"):
            total += pnl
        elif symbol.startswith("USD/"):
            total += pnl / close
        else:
            return None
    return total


def close_options(row, quotes, *, rv=False):
    opening_key = "opening_cash_flow" if rv else "open_cash_flow"
    try:
        total = float(row[opening_key])
    except (KeyError, TypeError, ValueError):
        return None
    for leg in row.get("legs", []):
        quote = quotes.get(leg.get("symbol"), {})
        side = str(leg.get("side", "")).upper()
        try:
            quantity = int(leg.get("quantity", 1))
            multiplier = float(leg.get("multiplier") or 100)
            price = float(quote["bid"] if side == "BUY" else quote["ask"])
        except (KeyError, TypeError, ValueError):
            return None
        total += (1 if side == "BUY" else -1) * price * multiplier * quantity
        if rv:
            total -= 0.65 * quantity
    return total


def closed_pnl(row):
    for key in ("pnl", "net_pnl_dollars", "pnl_usd", "pnl_dollars"):
        try:
            if row.get(key) is not None:
                return float(row[key])
        except (TypeError, ValueError):
            pass
    try:
        if row.get("return_fraction") is not None:
            return float(row["return_fraction"]) * 1000.0
    except (TypeError, ValueError):
        pass
    return None


def simulate_slots(trades):
    active, total, taken, skipped = [], 0.0, 0, 0
    ordered = sorted(trades, key=lambda item: (item["opened"], item["id"]))
    for order, trade in enumerate(ordered):
        while active and active[0][0] <= trade["opened"]:
            heapq.heappop(active)
        if len(active) >= SLOTS:
            skipped += 1
            continue
        heapq.heappush(active, (trade["closed"], order))
        total += trade["pnl"]
        taken += 1
    return {
        "signals": len(ordered), "taken": taken, "skipped": skipped,
        "pnl": total, "return_pct": total / STARTING_CASH * 100.0,
    }


def calculate(root="/data", day=None, as_of=None):
    root = Path(root)
    as_of = as_of or datetime.now(timezone.utc)
    day = day or as_of.astimezone(NY).date().isoformat()
    cutoff = min(as_of, cutoff_for(day)) if day == as_of.astimezone(NY).date().isoformat() else cutoff_for(day)
    marks = load_market_marks(root, day, cutoff)
    modules, sources = {}, {}
    diagnostics = {"main_unmarked": 0, "unmarked_by_engine": defaultdict(int)}

    entries, exits, sequence, names = {}, {}, {}, set()
    for row in read_json_lines(root / "paper_signal_outcomes.jsonl"):
        name = strategy_name(row)
        if name:
            names.add(name)
        setup = str(row.get("setup_id") or "")
        if not setup or market_day(row) != day:
            continue
        event = row.get("event_type")
        if event == "PAPER_ENTRY":
            sequence.setdefault(setup, len(sequence))
            entries[setup] = row
        elif event == "PAPER_EXIT":
            exits[setup] = row

    grouped = defaultdict(list)
    for setup, entry in entries.items():
        entry_time = opened_time(entry)
        if entry_time is None or entry_time > cutoff:
            continue
        recorded_exit = exits.get(setup)
        recorded_exit_time = parse_time((recorded_exit or {}).get("exit_timestamp"))
        if recorded_exit is not None and recorded_exit_time is not None and recorded_exit_time <= cutoff:
            exit_row = recorded_exit
            exit_timestamp, exit_price = exit_row.get("exit_timestamp"), exit_row.get("exit_price")
        else:
            exit_timestamp, exit_price = cutoff.isoformat(), marks["main_last"].get(entry.get("symbol"))
        if exit_price is None:
            diagnostics["main_unmarked"] += 1
            continue
        grouped[strategy_name(entry)].append({
            "setup_id": setup, "strategy_id": strategy_name(entry),
            "signal_timestamp": entry.get("signal_timestamp"),
            "entry_timestamp": entry.get("entry_timestamp"),
            "entry_price": entry.get("entry_price"), "stop_price": entry.get("stop_price"),
            "exit_timestamp": exit_timestamp, "exit_price": exit_price,
            "entry_sequence": sequence[setup],
        })

    try:
        names.update(json.loads((root / "strategy_runtime_diagnostics.json").read_text()).get("modules", {}))
    except (OSError, ValueError, TypeError):
        pass
    for name in names:
        result = simulate_day(grouped.get(name, []))
        modules[name] = {**result, "engine": "main"}
        sources[name] = "main"

    trades, modern_names = defaultdict(list), set()

    def add(name, opened, closed, pnl, engine, identifier):
        if not name or opened is None or pnl is None:
            return
        modern_names.add(name)
        sources[name] = engine
        trades[name].append({
            "opened": opened, "closed": closed or cutoff,
            "pnl": float(pnl), "engine": engine, "id": identifier,
        })

    specs = {
        "crosssection_paper_outcomes.jsonl": ("crosssection", lambda row: close_equity(row, marks)),
        "forex_paper_outcomes.jsonl": ("forex", lambda row: close_forex(row, marks["forex"])),
        "futures_curve_paper_outcomes.jsonl": ("futures_curve", lambda row: close_futures(row, marks["curves"])),
        "futures_paper_outcomes.jsonl": ("futures", lambda row: close_futures(row, marks["futures"])),
        "microstructure_paper_outcomes.jsonl": ("microstructure", lambda row: close_equity(row, marks)),
        "multi_leg_paper_outcomes.jsonl": ("multi_leg", lambda row: close_equity_legs(row, marks)),
        "options_paper_outcomes.jsonl": ("options", lambda row: close_options(row, marks["options"])),
        "short_paper_outcomes.jsonl": ("short", lambda row: close_equity(row, marks)),
        "statarb_paper_outcomes.jsonl": ("statarb", lambda row: close_equity_legs(row, marks)),
        "swing_paper_outcomes.jsonl": ("swing", lambda row: close_equity(row, marks)),
    }

    for filename, (engine, marker) in specs.items():
        opened, closed = {}, {}
        for row in read_json_lines(root / filename):
            name = strategy_name(row)
            if name:
                modern_names.add(name)
                sources.setdefault(name, engine)
            identifier = row_id(row)
            event = str(row.get("event_type") or row.get("event") or "").upper()
            if identifier and event in {"OPEN", "OPTION_ENTRY", "MULTI_LEG_ENTRY"}:
                opened[identifier] = row
            elif identifier and event in {"CLOSE", "OPTION_EXIT", "MULTI_LEG_EXIT"}:
                closed[identifier] = row
        for identifier, entry in opened.items():
            entry_time = opened_time(entry)
            if market_day(entry) != day or entry_time is None or entry_time > cutoff:
                continue
            exit_row = closed.get(identifier)
            recorded_close = parse_time(
                (exit_row or {}).get("closed_at") or (exit_row or {}).get("exit_timestamp") or
                (exit_row or {}).get("exit_time")
            ) if exit_row else None
            use_recorded_exit = exit_row is not None and recorded_close is not None and recorded_close <= cutoff
            pnl = closed_pnl(exit_row) if use_recorded_exit else marker(entry)
            closed_at = recorded_close if use_recorded_exit else cutoff
            if pnl is None:
                diagnostics["unmarked_by_engine"][engine] += 1
                continue
            add(strategy_name(entry), opened_time(entry), closed_at, pnl, engine, identifier)

    for row in read_json_lines(root / "event_paper_outcomes.jsonl"):
        name = strategy_name(row)
        if name:
            modern_names.add(name)
            sources.setdefault(name, "event")
        entry_time = opened_time(row)
        if market_day(row) != day or entry_time is None or entry_time > cutoff:
            continue
        recorded_close = parse_time(row.get("closed_at"))
        pnl = closed_pnl(row) if recorded_close is not None and recorded_close <= cutoff else None
        if pnl is None:
            quote = equity_quote(row.get("symbol"), marks)
            side = str(row.get("side", "")).upper()
            try:
                entry = float(row["entry_price"])
                close = float(quote["bid"] if side == "LONG" else quote["ask"])
                pnl = (1 if side == "LONG" else -1) * (close / entry - 1.0) * 1000.0
            except (KeyError, TypeError, ValueError):
                diagnostics["unmarked_by_engine"]["event"] += 1
                continue
        add(name, entry_time, recorded_close if recorded_close and recorded_close <= cutoff else cutoff,
            pnl, "event", row_id(row))

    rv_active = {}
    try:
        value = json.loads((root / "options_rv_paper_active.json").read_text())
        rv_active = value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        pass
    for row in read_json_lines(root / "options_rv_paper_outcomes.jsonl"):
        name = strategy_name(row)
        if name:
            modern_names.add(name)
            sources.setdefault(name, "options_rv")
        entry_time = opened_time(row)
        if market_day(row) == day and entry_time is not None and entry_time <= cutoff:
            recorded_close = parse_time(row.get("closed_at"))
            if recorded_close is not None and recorded_close <= cutoff:
                pnl = closed_pnl(row)
                closed_at = recorded_close
            else:
                pnl = close_options(row, marks["options"], rv=True)
                closed_at = cutoff
            if pnl is None:
                diagnostics["unmarked_by_engine"]["options_rv"] += 1
            else:
                add(name, entry_time, closed_at, pnl, "options_rv", row_id(row))
    for identifier, row in rv_active.items():
        name = strategy_name(row)
        if name:
            modern_names.add(name)
            sources.setdefault(name, "options_rv")
        entry_time = opened_time(row)
        if market_day(row) != day or entry_time is None or entry_time > cutoff:
            continue
        pnl = close_options(row, marks["options"], rv=True)
        if pnl is None:
            diagnostics["unmarked_by_engine"]["options_rv"] += 1
            continue
        add(name, entry_time, cutoff, pnl, "options_rv", str(identifier))

    for name in modern_names:
        modules[name] = {**simulate_slots(trades.get(name, [])), "engine": sources.get(name, "other")}

    ranked = sorted(modules.items(), key=lambda item: item[1]["return_pct"], reverse=True)
    return {
        "calculation_version": 1,
        "day": day,
        "as_of": cutoff.isoformat(),
        "starting_cash": STARTING_CASH,
        "method": "main=risk_sized; newer=five_reusable_1000_slots",
        "modules": dict(ranked),
        "module_count": len(modules),
        "diagnostics": {
            "main_unmarked": diagnostics["main_unmarked"],
            "unmarked_by_engine": dict(diagnostics["unmarked_by_engine"]),
        },
    }


def render_snapshot(snapshot):
    lines = [
        f"ALL-ENGINE HYPOTHETICAL CLOSE — {snapshot['day']}",
        f"As of: {snapshot['as_of']}",
        f"{'Rank':>4}  {'Module':<18} {'Engine':<16} {'Return':>9}",
        "-" * 55,
    ]
    for rank, (name, row) in enumerate(snapshot["modules"].items(), 1):
        lines.append(f"{rank:>4}  {name:<18} {row['engine']:<16} {row['return_pct']:>+8.2f}%")
    lines.extend([
        "-" * 55,
        f"Modules ranked: {snapshot['module_count']}",
        f"Main-ledger unavailable marks: {snapshot['diagnostics']['main_unmarked']}",
        "Other unavailable marks: " + (
            ", ".join(f"{key}={value}" for key, value in sorted(snapshot['diagnostics']['unmarked_by_engine'].items()))
            or "0"
        ),
    ])
    return "\n".join(lines) + "\n"
