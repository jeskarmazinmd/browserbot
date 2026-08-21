"""Snapshot-native MC1 momentum-continuation strategy."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta
import math

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .nearest_miss import consider, maximum, minimum, reset
from .snapshot_common import (
    Observation,
    make_signal,
    trim_before,
    value_at_or_before,
)


STRATEGY_ID = "MC1"
PAPER_ONLY = True

MC1_MAX_DISTANCE_FROM_10M_HIGH_PCT = 0.35
MC1_MIN_R2_30M = 0.55
MC1_MIN_RETURN_15M_PCT = 0.80
MC1_MIN_RETURN_5M_PCT = 0.25
NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"

TARGET_PCT = 0.80
STOP_PCT = 0.55
LOOKBACK_MINUTES = 30


@dataclass
class _State:
    observations: deque[Observation] = field(default_factory=deque)


def _simple_return_pct(old_price: float, new_price: float) -> float:
    if old_price <= 0:
        return math.nan
    return (new_price / old_price - 1.0) * 100.0


def _fit_log_slope_r2(prices: list[float]) -> tuple[float, float]:
    if len(prices) < 2 or any(price <= 0 for price in prices):
        return math.nan, math.nan

    logs = [math.log(price) for price in prices]
    x = list(range(len(logs)))

    x_mean = sum(x) / len(x)
    y_mean = sum(logs) / len(logs)

    denominator = sum(
        (value - x_mean) ** 2
        for value in x
    )

    if denominator == 0:
        return math.nan, math.nan

    slope = sum(
        (a - x_mean) * (b - y_mean)
        for a, b in zip(x, logs)
    ) / denominator

    fitted = [
        y_mean + slope * (value - x_mean)
        for value in x
    ]

    ss_res = sum(
        (actual - predicted) ** 2
        for actual, predicted in zip(logs, fitted)
    )
    ss_tot = sum(
        (actual - y_mean) ** 2
        for actual in logs
    )

    r2 = 1.0 - ss_res / ss_tot if ss_tot else 0.0
    slope_pct_hour = (math.exp(slope * 60.0) - 1.0) * 100.0

    return slope_pct_hour, r2


def _minute_prices(
    observations: deque[Observation],
    timestamp,
) -> list[float] | None:

    window_start = timestamp - timedelta(minutes=LOOKBACK_MINUTES)

    if (
        not observations
        or observations[0].timestamp > window_start
    ):
        return None

    prices = []

    for minutes_ago in range(LOOKBACK_MINUTES, -1, -1):
        item = value_at_or_before(
            observations,
            timestamp - timedelta(minutes=minutes_ago),
        )

        if item is None:
            return None

        prices.append(float(item.price))

    return prices


class MC1Strategy(EventStrategy):

    name = STRATEGY_ID

    def __init__(self):
        self._state = defaultdict(_State)

    def on_snapshot(
        self,
        snapshot: MarketSnapshot,
    ) -> list[SignalEvent]:

        out = []; reset(self)

        for symbol, quote in snapshot.quotes.items():
            state = self._state[symbol]

            state.observations.append(
                Observation(
                    snapshot.timestamp,
                    float(quote.price),
                    quote.total_volume,
                )
            )

            trim_before(
                state.observations,
                snapshot.timestamp
                - timedelta(minutes=LOOKBACK_MINUTES + 5),
            )

            prices = _minute_prices(
                state.observations,
                snapshot.timestamp,
            )

            if prices is None:
                continue

            current_price = float(quote.price)
            ret15 = _simple_return_pct(prices[-16], prices[-1])
            ret5 = _simple_return_pct(prices[-6], prices[-1])

            _, r2_30 = _fit_log_slope_r2(prices)

            high10 = max(prices[-10:])

            distance_high = (
                (high10 / current_price - 1.0) * 100.0
                if current_price > 0
                else math.nan
            )

            consider(self,symbol,snapshot.timestamp,current_price,[minimum("return_15m_pct",ret15,MC1_MIN_RETURN_15M_PCT,"%"),minimum("return_5m_pct",ret5,MC1_MIN_RETURN_5M_PCT,"%"),minimum("r2_30m",r2_30,MC1_MIN_R2_30M),maximum("distance_from_10m_high_pct",distance_high,MC1_MAX_DISTANCE_FROM_10M_HIGH_PCT,"%")])

            if (
                ret15 >= MC1_MIN_RETURN_15M_PCT
                and ret5 >= MC1_MIN_RETURN_5M_PCT
                and r2_30 >= MC1_MIN_R2_30M
                and (
                    distance_high
                    <= MC1_MAX_DISTANCE_FROM_10M_HIGH_PCT
                )
            ):
                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        current_price,
                        TARGET_PCT,
                        STOP_PCT,
                        "momentum_continuation",
                        return_15m_pct=ret15,
                        return_5m_pct=ret5,
                        r2_30m=r2_30,
                        distance_from_10m_high_pct=distance_high,
                        forward_start_utc=(
                            NEW_RESEARCH_FORWARD_START_UTC
                        ),
                    )
                )

        return out
