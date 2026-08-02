"""Snapshot-native VT1 trendline/mean confluence strategy."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta
import math

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .snapshot_common import (
    Observation,
    make_signal,
    trim_before,
    value_at_or_before,
)


STRATEGY_ID = "VT1"
PAPER_ONLY = True

NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"
VT1_MAX_CONFLUENCE_DISTANCE_PCT = 0.20
VT1_MIN_R2_45M = 0.45
VT1_MIN_REBOUND_2M_PCT = 0.10

LOOKBACK_MINUTES = 45
TARGET_PCT = 0.80
STOP_PCT = 0.55


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


def _fit_log_trend(
    prices: list[float],
) -> tuple[float, float, float, float]:

    if len(prices) < 2 or any(price <= 0 for price in prices):
        return math.nan, math.nan, math.nan, math.nan

    logs = [math.log(price) for price in prices]
    x = list(range(len(logs)))

    x_mean = sum(x) / len(x)
    y_mean = sum(logs) / len(logs)

    denominator = sum(
        (value - x_mean) ** 2
        for value in x
    )

    if denominator == 0:
        return math.nan, math.nan, math.nan, math.nan

    slope = sum(
        (a - x_mean) * (b - y_mean)
        for a, b in zip(x, logs)
    ) / denominator

    intercept = y_mean - slope * x_mean

    fitted = [
        intercept + slope * value
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
    trend_now = math.exp(intercept + slope * x[-1])

    return slope, slope_pct_hour, r2, trend_now


class VT1Strategy(EventStrategy):

    name = STRATEGY_ID

    def __init__(self):
        self._state = defaultdict(_State)

    def on_snapshot(
        self,
        snapshot: MarketSnapshot,
    ) -> list[SignalEvent]:

        out = []

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

            slope, slope45, r2_45, trend_now = _fit_log_trend(
                prices
            )

            current_price = float(quote.price)
            mean30 = sum(prices[-30:]) / 30.0

            trend_dist = (
                abs(current_price / trend_now - 1.0) * 100.0
                if trend_now > 0
                else math.nan
            )

            mean_dist = (
                abs(current_price / mean30 - 1.0) * 100.0
                if mean30 > 0
                else math.nan
            )

            rebound2 = _simple_return_pct(
                prices[-3],
                prices[-1],
            )

            if (
                slope > 0
                and r2_45 >= VT1_MIN_R2_45M
                and trend_dist <= VT1_MAX_CONFLUENCE_DISTANCE_PCT
                and mean_dist <= VT1_MAX_CONFLUENCE_DISTANCE_PCT
                and rebound2 >= VT1_MIN_REBOUND_2M_PCT
            ):
                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        current_price,
                        TARGET_PCT,
                        STOP_PCT,
                        "trendline_mean_confluence",
                        slope_45m_pct_per_hour=slope45,
                        r2_45m=r2_45,
                        trendline_price=trend_now,
                        rolling_mean_30m=mean30,
                        distance_to_trendline_pct=trend_dist,
                        distance_to_mean_pct=mean_dist,
                        rebound_2m_pct=rebound2,
                        forward_start_utc=(
                            NEW_RESEARCH_FORWARD_START_UTC
                        ),
                    )
                )

        return out
