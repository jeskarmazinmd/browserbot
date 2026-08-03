"""Snapshot-native AV1 volatility-adaptive rebound strategy."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta
import math

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .nearest_miss import boolean, consider, minimum, reset
from .snapshot_common import (
    Observation,
    make_signal,
    trim_before,
    value_at_or_before,
)


STRATEGY_ID = "AV1"
PAPER_ONLY = True

AV1_MIN_DRAWDOWN_PCT = 0.40
AV1_MIN_REBOUND_2M_PCT = 0.10
AV1_VOLATILITY_MULTIPLIER = 2.0
NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"

LOOKBACK_MINUTES = 30
TARGET_PCT = 0.75
STOP_PCT = 0.60


@dataclass
class _State:
    observations: deque[Observation] = field(default_factory=deque)


def _simple_return_pct(old_price: float, new_price: float) -> float:
    if old_price <= 0:
        return math.nan
    return (new_price / old_price - 1.0) * 100.0


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


def _log_slope_pct_per_hour(prices: list[float]) -> float:
    if len(prices) < 2 or any(price <= 0 for price in prices):
        return math.nan

    logs = [math.log(price) for price in prices]
    x = list(range(len(logs)))

    x_mean = sum(x) / len(x)
    y_mean = sum(logs) / len(logs)

    denominator = sum(
        (value - x_mean) ** 2
        for value in x
    )

    if denominator == 0:
        return math.nan

    slope = sum(
        (a - x_mean) * (b - y_mean)
        for a, b in zip(x, logs)
    ) / denominator

    return (math.exp(slope * 60.0) - 1.0) * 100.0


def _population_std(values: list[float]) -> float:
    if not values:
        return math.nan

    average = sum(values) / len(values)

    return math.sqrt(
        sum((value - average) ** 2 for value in values)
        / len(values)
    )


class AV1Strategy(EventStrategy):

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

            returns_1m = [
                _simple_return_pct(previous, current)
                for previous, current in zip(prices, prices[1:])
            ]

            sigma = (
                _population_std(returns_1m)
                if len(returns_1m) >= 10
                else math.nan
            )

            high15 = max(prices[-16:])
            low5 = min(prices[-6:])

            drawdown = (
                (high15 / low5 - 1.0) * 100.0
                if low5 > 0
                else math.nan
            )

            rebound2 = _simple_return_pct(
                prices[-3],
                prices[-1],
            )

            slope30 = _log_slope_pct_per_hour(prices)

            required_drawdown = (
                max(
                    AV1_MIN_DRAWDOWN_PCT,
                    AV1_VOLATILITY_MULTIPLIER * sigma,
                )
                if not math.isnan(sigma)
                else math.inf
            )

            required_rebound = (
                max(
                    AV1_MIN_REBOUND_2M_PCT,
                    0.5 * sigma,
                )
                if not math.isnan(sigma)
                else math.inf
            )

            consider(self,symbol,snapshot.timestamp,float(quote.price),[boolean("positive_30m_slope",slope30>0),minimum("drawdown_pct",drawdown,required_drawdown,"%"),minimum("rebound_2m_pct",rebound2,required_rebound,"%")])

            if (
                slope30 > 0
                and drawdown >= required_drawdown
                and rebound2 >= required_rebound
            ):
                current_price = float(quote.price)

                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        current_price,
                        TARGET_PCT,
                        STOP_PCT,
                        "volatility_adaptive_rebound",
                        recent_sigma_1m_pct=sigma,
                        drawdown_15m_to_5m_low_pct=drawdown,
                        required_drawdown_pct=required_drawdown,
                        rebound_2m_pct=rebound2,
                        required_rebound_pct=required_rebound,
                        forward_start_utc=(
                            NEW_RESEARCH_FORWARD_START_UTC
                        ),
                    )
                )

        return out
