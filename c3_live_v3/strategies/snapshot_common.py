"""Shared mechanics for snapshot-native strategies.

This module contains transport-neutral helpers only. Strategy rules and retained
state remain in each strategy class.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Deque, Iterable

from engine.events import MarketSnapshot, Quote, SignalEvent


@dataclass(frozen=True)
class Observation:
    timestamp: datetime
    price: float
    total_volume: float | None


def trim_before(items: Deque[Observation], cutoff: datetime) -> None:
    while len(items) > 1 and items[1].timestamp < cutoff:
        items.popleft()


def value_at_or_before(items: Iterable[Observation], timestamp: datetime) -> Observation | None:
    answer = None
    for item in items:
        if item.timestamp <= timestamp:
            answer = item
        else:
            break
    return answer


def prices_since(items: Iterable[Observation], cutoff: datetime) -> list[float]:
    return [item.price for item in items if item.timestamp >= cutoff]


def time_weighted_mean(items: Iterable[Observation], start: datetime, end: datetime) -> float | None:
    """Piecewise-constant time-weighted price mean over [start, end]."""
    data = list(items)
    if not data or end <= start:
        return None

    anchor = value_at_or_before(data, start)
    if anchor is None:
        first_after = next((item for item in data if item.timestamp >= start), None)
        if first_after is None:
            return None
        current_price = first_after.price
        current_time = first_after.timestamp
    else:
        current_price = anchor.price
        current_time = start

    weighted = 0.0
    seconds = 0.0
    for item in data:
        if item.timestamp <= current_time:
            continue
        if item.timestamp > end:
            break
        dt = (item.timestamp - current_time).total_seconds()
        if dt > 0:
            weighted += current_price * dt
            seconds += dt
        current_price = item.price
        current_time = item.timestamp

    if current_time < end:
        dt = (end - current_time).total_seconds()
        weighted += current_price * dt
        seconds += dt

    return weighted / seconds if seconds > 0 else None


def ema_time_constant_seconds(span_minutes: float) -> float:
    """Continuous-time constant matching a standard span EMA at 60s sampling."""
    alpha_60 = 2.0 / (float(span_minutes) + 1.0)
    return -60.0 / math.log(1.0 - alpha_60)


def update_time_ema(previous: float | None, price: float, dt_seconds: float, span_minutes: float) -> float:
    if previous is None or dt_seconds <= 0:
        return float(price) if previous is None else float(previous)
    tau = ema_time_constant_seconds(span_minutes)
    alpha = 1.0 - math.exp(-float(dt_seconds) / tau)
    return alpha * float(price) + (1.0 - alpha) * float(previous)


def cumulative_volume_rate(previous: Observation | None, current: Observation) -> float | None:
    if previous is None or previous.total_volume is None or current.total_volume is None:
        return None
    dt = (current.timestamp - previous.timestamp).total_seconds()
    dv = float(current.total_volume) - float(previous.total_volume)
    if dt <= 0 or dv < 0:  # negative means session reset/correction
        return None
    return dv / dt


def make_signal(
    snapshot: MarketSnapshot,
    strategy_id: str,
    symbol: str,
    price: float,
    target_pct: float,
    stop_pct: float,
    setup: str,
    **metrics,
) -> SignalEvent:
    price = float(price)
    return SignalEvent(
        timestamp=snapshot.timestamp,
        strategy_id=strategy_id,
        symbol=str(symbol),
        signal_type="SIGNAL",
        data={
            "entry_price": price,
            "target_price": price * (1.0 + float(target_pct) / 100.0),
            "stop_price": price * (1.0 - float(stop_pct) / 100.0),
            "setup": setup,
            "live_order_placement": False,
            **metrics,
        },
    )
