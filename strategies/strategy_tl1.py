"""Snapshot-native TL1 uptrend-line reclaim strategy."""

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


STRATEGY_ID = "TL1"
PAPER_ONLY = True

NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"
TL1_MIN_PRIOR_GAP_BELOW_TREND_PCT = 0.25
TL1_MIN_R2_30M = 0.45

LOOKBACK_MINUTES = 30
TARGET_PCT = 0.75
STOP_PCT = 0.50


@dataclass
class _State:
    observations: deque[Observation] = field(default_factory=deque)


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
) -> tuple[float, float, float, list[float]]:

    if len(prices) < 2 or any(price <= 0 for price in prices):
        return math.nan, math.nan, math.nan, []

    logs = [math.log(price) for price in prices]
    x = list(range(len(logs)))

    x_mean = sum(x) / len(x)
    y_mean = sum(logs) / len(logs)

    denominator = sum(
        (value - x_mean) ** 2
        for value in x
    )

    if denominator == 0:
        return math.nan, math.nan, math.nan, []

    slope = sum(
        (a - x_mean) * (b - y_mean)
        for a, b in zip(x, logs)
    ) / denominator

    intercept = y_mean - slope * x_mean

    fitted_logs = [
        intercept + slope * value
        for value in x
    ]

    ss_res = sum(
        (actual - predicted) ** 2
        for actual, predicted in zip(logs, fitted_logs)
    )
    ss_tot = sum(
        (actual - y_mean) ** 2
        for actual in logs
    )

    r2 = 1.0 - ss_res / ss_tot if ss_tot else 0.0
    slope_pct_hour = (math.exp(slope * 60.0) - 1.0) * 100.0
    trend = [math.exp(value) for value in fitted_logs]

    return slope, slope_pct_hour, r2, trend


class TL1Strategy(EventStrategy):

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

            slope, slope30, r2_30, trend = _fit_log_trend(prices)

            if not trend:
                continue

            current_price = float(quote.price)

            prior_gap = (
                (trend[-2] / prices[-2] - 1.0) * 100.0
                if prices[-2] > 0
                else math.nan
            )

            crossed = (
                prices[-2] < trend[-2]
                and current_price >= trend[-1]
            )

            if (
                slope > 0
                and r2_30 >= TL1_MIN_R2_30M
                and (
                    prior_gap
                    >= TL1_MIN_PRIOR_GAP_BELOW_TREND_PCT
                )
                and crossed
            ):
                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        current_price,
                        TARGET_PCT,
                        STOP_PCT,
                        "uptrend_line_reclaim",
                        r2_30m=r2_30,
                        slope_30m_pct_per_hour=slope30,
                        prior_gap_below_trendline_pct=prior_gap,
                        trendline_price_now=trend[-1],
                        forward_start_utc=(
                            NEW_RESEARCH_FORWARD_START_UTC
                        ),
                    )
                )

        return out
