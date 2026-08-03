"""Snapshot-native CV1 selloff-curvature reversal strategy."""

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


STRATEGY_ID = "CV1"
PAPER_ONLY = True

CV1_MIN_REBOUND_FROM_LOW_PCT = 0.25
CV1_MIN_SLOPE_IMPROVEMENT_PCT_PER_HOUR = 0.80
NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"

LOOKBACK_MINUTES = 20
TARGET_PCT = 0.70
STOP_PCT = 0.55


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


def _fit_log_slope_r2(
    prices: list[float],
) -> tuple[float, float]:

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


class CV1Strategy(EventStrategy):

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

            # Legacy slices: [-21:-10] and tail(11), sharing midpoint.
            early_slope, early_r2 = _fit_log_slope_r2(
                prices[:11]
            )
            late_slope, late_r2 = _fit_log_slope_r2(
                prices[10:]
            )

            low20 = min(prices)
            current_price = float(quote.price)

            rebound_low = (
                (current_price / low20 - 1.0) * 100.0
                if low20 > 0
                else math.nan
            )
            improvement = late_slope - early_slope

            consider(self,symbol,snapshot.timestamp,current_price,[boolean("early_slope_negative",early_slope<0),minimum("slope_improvement_pct_per_hour",improvement,CV1_MIN_SLOPE_IMPROVEMENT_PCT_PER_HOUR,"%/hour"),minimum("rebound_from_low_pct",rebound_low,CV1_MIN_REBOUND_FROM_LOW_PCT,"%")])

            if (
                early_slope < 0
                and (
                    improvement
                    >= CV1_MIN_SLOPE_IMPROVEMENT_PCT_PER_HOUR
                )
                and rebound_low >= CV1_MIN_REBOUND_FROM_LOW_PCT
            ):
                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        current_price,
                        TARGET_PCT,
                        STOP_PCT,
                        "selloff_curvature_reversal",
                        early_slope_pct_per_hour=early_slope,
                        late_slope_pct_per_hour=late_slope,
                        slope_improvement_pct_per_hour=improvement,
                        early_r2=early_r2,
                        late_r2=late_r2,
                        rebound_from_20m_low_pct=rebound_low,
                        forward_start_utc=(
                            NEW_RESEARCH_FORWARD_START_UTC
                        ),
                    )
                )

        return out
