#!/usr/bin/env python3
"""Offline event study for confirmed multi-minute cascade reversals.

This script is deliberately separate from the strategy registry and workers.  It
streams saved quote tapes, builds minute bars, detects one broad pre-declared
pattern, and measures forward returns.  Historical results are research only;
prospective validation is still required before creating a paper strategy.
"""

from __future__ import annotations

import argparse
import csv
import glob
import gzip
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Iterable


@dataclass
class Bar:
    minute: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass
class Event:
    symbol: str
    minute: datetime
    entry: float
    cascade_pct: float
    down_minutes: int
    spy_cascade_pct: float | None
    returns: dict[int, float]
    mfe_pct: float
    mae_pct: float


def _minute_from_iso(value: str) -> datetime:
    # Quote tapes use UTC ISO timestamps.  Truncating before parsing is much
    # faster than parsing every sub-second timestamp in a large tape.
    value = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(second=0, microsecond=0)


def load_minute_bars(paths: Iterable[str]) -> dict[str, list[Bar]]:
    raw: dict[str, dict[datetime, list[float]]] = defaultdict(dict)
    for path_string in paths:
        path = Path(path_string)
        print(f"Reading {path} ...", flush=True)
        if path.suffix.lower() == ".gz":
            handle_context = gzip.open(
                path, "rt", encoding="utf-8", errors="ignore", newline=""
            )
        else:
            handle_context = path.open(
                "r", encoding="utf-8", errors="ignore", newline=""
            )
        with handle_context as handle:
            reader = csv.DictReader((line.replace("\x00", "") for line in handle))
            for row in reader:
                try:
                    symbol = str(row.get("symbol", "")).strip().upper()
                    raw_price = next(
                        row.get(name)
                        for name in (
                            "legacy_price",
                            "last_price",
                            "last",
                            "mark",
                            "regular_last",
                        )
                        if row.get(name) not in (None, "")
                    )
                    price = float(raw_price)
                    raw_minute = row.get("market_minute_utc") or row.get("timestamp_utc")
                    minute = _minute_from_iso(str(raw_minute or ""))
                except (StopIteration, TypeError, ValueError):
                    continue
                if not symbol or not math.isfinite(price) or price <= 0:
                    continue
                values = raw[symbol].get(minute)
                if values is None:
                    raw[symbol][minute] = [price, price, price, price]
                else:
                    values[1] = max(values[1], price)
                    values[2] = min(values[2], price)
                    values[3] = price

    result: dict[str, list[Bar]] = {}
    for symbol, minutes in raw.items():
        result[symbol] = [
            Bar(minute, values[0], values[1], values[2], values[3])
            for minute, values in sorted(minutes.items())
        ]
    return result


def _contiguous(bars: list[Bar], start: int, end: int) -> bool:
    return all(
        bars[index].minute - bars[index - 1].minute == timedelta(minutes=1)
        for index in range(start + 1, end + 1)
    )


def _cascade(window: list[Bar]) -> float:
    peak = max(bar.high for bar in window)
    trough = min(bar.low for bar in window)
    return 100.0 * (trough / peak - 1.0)


def detect_events(
    bars_by_symbol: dict[str, list[Bar]],
    *,
    window_minutes: int = 10,
    min_drop_pct: float = 0.75,
    min_down_minutes: int = 6,
    near_low_bps: float = 10.0,
    max_single_minute_drop_pct: float = 0.50,
    max_spy_drop_pct: float = 0.50,
    cooldown_minutes: int = 20,
    horizons: tuple[int, ...] = (1, 5, 10, 15, 20),
    cost_bps: float = 10.0,
) -> list[Event]:
    events: list[Event] = []
    spy_by_minute = {bar.minute: bar for bar in bars_by_symbol.get("SPY", [])}
    longest = max(horizons)

    for symbol, bars in sorted(bars_by_symbol.items()):
        if symbol == "SPY" or len(bars) <= window_minutes + longest:
            continue
        last_event: datetime | None = None
        for index in range(window_minutes, len(bars) - longest):
            # The cascade ends on the prior minute.  The current positive close
            # is confirmation, and its close is the modeled entry.
            start = index - window_minutes
            if not _contiguous(bars, start, index + longest):
                continue
            prior = bars[start:index]
            confirmation = bars[index]
            prior_close = bars[index - 1].close
            if confirmation.close <= prior_close:
                continue

            cascade_pct = _cascade(prior)
            if cascade_pct > -min_drop_pct:
                continue

            minute_returns = [
                100.0 * (bars[pos].close / bars[pos - 1].close - 1.0)
                for pos in range(start + 1, index)
            ]
            down_minutes = sum(value < 0 for value in minute_returns)
            if down_minutes < min_down_minutes:
                continue
            if minute_returns and min(minute_returns) < -max_single_minute_drop_pct:
                continue

            rolling_low = min(bar.low for bar in prior)
            distance_from_low_bps = 10000.0 * (prior_close / rolling_low - 1.0)
            if distance_from_low_bps > near_low_bps:
                continue

            spy_window = [spy_by_minute.get(bar.minute) for bar in prior]
            spy_cascade = None
            if all(spy_window):
                spy_cascade = _cascade([bar for bar in spy_window if bar is not None])
                if spy_cascade < -max_spy_drop_pct:
                    continue

            if last_event and confirmation.minute - last_event < timedelta(minutes=cooldown_minutes):
                continue

            entry = confirmation.close
            net_returns = {
                horizon: 100.0 * (bars[index + horizon].close / entry - 1.0)
                - cost_bps / 100.0
                for horizon in horizons
            }
            future = bars[index + 1 : index + longest + 1]
            mfe = 100.0 * (max(bar.high for bar in future) / entry - 1.0)
            mae = 100.0 * (min(bar.low for bar in future) / entry - 1.0)
            events.append(
                Event(
                    symbol=symbol,
                    minute=confirmation.minute,
                    entry=entry,
                    cascade_pct=cascade_pct,
                    down_minutes=down_minutes,
                    spy_cascade_pct=spy_cascade,
                    returns=net_returns,
                    mfe_pct=mfe,
                    mae_pct=mae,
                )
            )
            last_event = confirmation.minute
    return events


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def print_report(events: list[Event], horizons: tuple[int, ...]) -> None:
    print("\nCASCADE REVERSAL EVENT STUDY")
    print("=" * 94)
    print(f"Independent events: {len(events)}")
    print(f"Trading days:       {len({event.minute.date() for event in events})}")
    print(f"Symbols:            {len({event.symbol for event in events})}")
    if not events:
        return
    print("\nNET FORWARD RETURNS (round-trip cost already deducted)")
    print("HORIZON   MEAN%   MEDIAN%   WIN%   WORST%   BEST%")
    for horizon in horizons:
        values = [event.returns[horizon] for event in events]
        wins = 100.0 * sum(value > 0 for value in values) / len(values)
        print(
            f"{horizon:>4}m   {_mean(values):+7.3f}  {median(values):+8.3f} "
            f"{wins:6.1f}  {min(values):+7.3f} {max(values):+7.3f}"
        )
    print(f"\nMedian 20m MFE: {median(event.mfe_pct for event in events):+.3f}%")
    print(f"Median 20m MAE: {median(event.mae_pct for event in events):+.3f}%")
    print("\nEVENTS")
    print("UTC TIME                 SYMBOL  DROP% DOWN  SPY%  " + " ".join(f"R{h}m%" for h in horizons))
    for event in sorted(events, key=lambda item: item.minute):
        spy = "   NA" if event.spy_cascade_pct is None else f"{event.spy_cascade_pct:+5.2f}"
        returns = " ".join(f"{event.returns[h]:+6.2f}" for h in horizons)
        print(
            f"{event.minute.isoformat():24s} {event.symbol:6s} "
            f"{event.cascade_pct:+6.2f} {event.down_minutes:4d} {spy} {returns}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tape-glob", default="/data/tapes/quotes_*.csv")
    parser.add_argument("--window-minutes", type=int, default=10)
    parser.add_argument("--min-drop-pct", type=float, default=0.75)
    parser.add_argument("--min-down-minutes", type=int, default=6)
    parser.add_argument("--near-low-bps", type=float, default=10.0)
    parser.add_argument("--max-single-minute-drop-pct", type=float, default=0.50)
    parser.add_argument("--max-spy-drop-pct", type=float, default=0.50)
    parser.add_argument("--cooldown-minutes", type=int, default=20)
    parser.add_argument("--cost-bps", type=float, default=10.0)
    parser.add_argument("--horizons", default="1,5,10,15,20")
    args = parser.parse_args()

    paths = sorted(glob.glob(args.tape_glob))
    if not paths:
        raise SystemExit(f"No quote tapes matched {args.tape_glob!r}")
    horizons = tuple(sorted({int(value) for value in args.horizons.split(",") if value}))
    # Process one tape at a time so a multi-day study cannot retain every
    # minute bar in production memory at once.
    events: list[Event] = []
    for path in paths:
        bars = load_minute_bars([path])
        events.extend(
            detect_events(
                bars,
                window_minutes=args.window_minutes,
                min_drop_pct=args.min_drop_pct,
                min_down_minutes=args.min_down_minutes,
                near_low_bps=args.near_low_bps,
                max_single_minute_drop_pct=args.max_single_minute_drop_pct,
                max_spy_drop_pct=args.max_spy_drop_pct,
                cooldown_minutes=args.cooldown_minutes,
                horizons=horizons,
                cost_bps=args.cost_bps,
            )
        )
    print_report(events, horizons)


if __name__ == "__main__":
    main()
