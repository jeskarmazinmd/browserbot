"""Finite-capital paper-performance simulation."""

from __future__ import annotations

from datetime import datetime
import heapq
import math
import statistics


STARTING_CASH = 5000.0
RISK_FRACTION = 0.01
MAX_POSITION_FRACTION = 0.20


def _timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _effective_entry_timestamp(row):
    if "entry_timestamp" in row:
        return _timestamp(row.get("entry_timestamp"))
    if row.get("exit_model") == "second_leg":
        return _timestamp(row.get("second_leg_entry_time"))
    return _timestamp(row.get("signal_timestamp"))


def simulate_day(
    rows,
    starting_cash=STARTING_CASH,
    risk_fraction=RISK_FRACTION,
    max_position_fraction=MAX_POSITION_FRACTION,
):
    prepared = []

    for fallback_sequence, row in enumerate(rows):
        entry_time = _effective_entry_timestamp(row)
        exit_time = _timestamp(row.get("exit_timestamp"))
        try:
            entry = float(row["entry_price"])
            exit_price = float(row["exit_price"])
            stop = float(row["stop_price"])
        except (KeyError, TypeError, ValueError):
            continue

        if (
            entry_time is None
            or exit_time is None
            or entry <= 0
            or exit_price <= 0
            or exit_time < entry_time
        ):
            continue

        sequence = row.get("entry_sequence")
        if sequence is None:
            sequence = fallback_sequence

        prepared.append(
            (
                entry_time,
                int(sequence),
                str(row.get("setup_id") or ""),
                exit_time,
                entry,
                exit_price,
                stop,
            )
        )

    prepared.sort(key=lambda item: (item[0], item[1], item[2]))

    cash = float(starting_cash)
    deployed = 0.0
    active = []
    taken = 0
    skipped = 0
    max_positions = 0
    peak_deployed = 0.0
    peak_equity = float(starting_cash)
    max_drawdown_pct = 0.0
    holds = []

    def record_equity():
        nonlocal peak_equity, max_drawdown_pct
        equity = cash + deployed
        peak_equity = max(peak_equity, equity)
        if peak_equity > 0:
            drawdown = (peak_equity - equity) / peak_equity * 100.0
            max_drawdown_pct = max(max_drawdown_pct, drawdown)

    def release_until(timestamp):
        nonlocal cash, deployed
        while active and active[0][0] <= timestamp:
            _, _, shares, entry, exit_price = heapq.heappop(active)
            cash += shares * exit_price
            deployed -= shares * entry
            record_equity()

    for order, item in enumerate(prepared):
        entry_time, _, _, exit_time, entry, exit_price, stop = item
        release_until(entry_time)

        equity = cash + deployed
        risk_per_share = abs(entry - stop)

        if risk_per_share <= 0 or not math.isfinite(risk_per_share):
            skipped += 1
            continue

        risk_shares = math.floor(equity * risk_fraction / risk_per_share)
        position_shares = math.floor(
            equity * max_position_fraction / entry
        )
        cash_shares = math.floor(cash / entry)
        shares = min(risk_shares, position_shares, cash_shares)

        if shares < 1:
            skipped += 1
            continue

        cost = shares * entry
        cash -= cost
        deployed += cost
        taken += 1
        holds.append((exit_time - entry_time).total_seconds())

        heapq.heappush(
            active,
            (exit_time, order, shares, entry, exit_price),
        )

        max_positions = max(max_positions, len(active))
        peak_deployed = max(peak_deployed, deployed)
        record_equity()

    release_until(datetime.max.replace(tzinfo=prepared[0][0].tzinfo) if prepared else datetime.max)

    one_share_pnl = sum(item[5] - item[4] for item in prepared)
    end_equity = cash + deployed

    return {
        "signals": len(prepared),
        "taken": taken,
        "skipped": skipped,
        "end_equity": end_equity,
        "return_pct": (end_equity / starting_cash - 1.0) * 100.0,
        "max_drawdown_pct": max_drawdown_pct,
        "peak_deployed": peak_deployed,
        "max_positions": max_positions,
        "median_hold_seconds": statistics.median(holds) if holds else 0.0,
        "one_share_pnl": one_share_pnl,
        "one_share_return_pct": one_share_pnl / starting_cash * 100.0,
    }
