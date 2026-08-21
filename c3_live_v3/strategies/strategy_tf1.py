"""TF1 trend-pullback research strategy.

Snapshot-native version.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta
import math

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .nearest_miss import between, boolean, consider, minimum, reset
from .snapshot_common import Observation, make_signal, trim_before, prices_since


STRATEGY_ID = "TF1"
NAME = "Trend Pullback"
VERSION = 1
PAPER_ONLY = True
DESCRIPTION = "Orderly 30-minute uptrend, shallow pullback, then renewed rise."

MIN_RETURN_30M_PCT = 0.75
MIN_R2 = 0.60
PULLBACK_MIN_PCT = 0.25
PULLBACK_MAX_PCT = 0.75
REBOUND_2M_PCT = 0.10
TARGET_PCT = 0.75
STOP_PCT = 0.60


@dataclass
class _State:
    observations: deque[Observation] = field(default_factory=deque)


def _simple_return_pct(old_price: float, new_price: float) -> float:
    if old_price <= 0:
        return math.nan
    return (float(new_price) / float(old_price) - 1.0) * 100.0


def _return_pct(prices: list[float]) -> float:
    if len(prices) < 2 or prices[0] <= 0:
        return math.nan
    return (prices[-1] / prices[0] - 1.0) * 100.0


def _fit_slope_r2(prices: list[float]) -> tuple[float, float]:
    if len(prices) < 2:
        return math.nan, math.nan

    y = [math.log(p) for p in prices if p > 0]

    if len(y) < 2:
        return math.nan, math.nan

    x = list(range(len(y)))

    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)

    numerator = sum(
        (a - x_mean) * (b - y_mean)
        for a, b in zip(x, y)
    )

    denominator = sum(
        (a - x_mean) ** 2
        for a in x
    )

    if denominator == 0:
        return math.nan, math.nan

    slope = numerator / denominator

    fitted = [
        y_mean + slope * (a - x_mean)
        for a in x
    ]

    ss_res = sum(
        (actual - predicted) ** 2
        for actual, predicted in zip(y, fitted)
    )

    ss_tot = sum(
        (actual - y_mean) ** 2
        for actual in y
    )

    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # convert log slope per minute into percent/hour
    slope_pct_hour = (
        (math.exp(slope * 60.0) - 1.0) * 100.0
    )

    return slope_pct_hour, r2


class TF1Strategy(EventStrategy):

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

            current = Observation(
                snapshot.timestamp,
                float(quote.price),
                quote.total_volume,
            )

            state.observations.append(current)

            trim_before(
                state.observations,
                snapshot.timestamp - timedelta(minutes=60),
            )

            prices_30m = prices_since(
                state.observations,
                snapshot.timestamp - timedelta(minutes=30),
            )

            if len(prices_30m) < 31:
                continue

            current_price = current.price

            return_30m_pct = _return_pct(prices_30m)

            slope_30m_pct_per_hour, r2_30m = _fit_slope_r2(
                prices_30m
            )

            prices_10m = prices_since(
                state.observations,
                snapshot.timestamp - timedelta(minutes=10),
            )

            if not prices_10m:
                continue

            recent_high = max(prices_10m)

            pullback_pct = (
                (recent_high / current_price - 1.0) * 100.0
                if current_price > 0
                else math.nan
            )

            prices_2m = prices_since(
                state.observations,
                snapshot.timestamp - timedelta(minutes=2),
            )

            if len(prices_2m) < 3:
                continue

            rebound_2m_pct = _simple_return_pct(
                prices_2m[0],
                prices_2m[-1],
            )

            consider(self,symbol,snapshot.timestamp,current_price,[minimum("return_30m_pct",return_30m_pct,MIN_RETURN_30M_PCT,"%"),boolean("positive_slope",slope_30m_pct_per_hour>0),minimum("r2_30m",r2_30m,MIN_R2),between("pullback_pct",pullback_pct,PULLBACK_MIN_PCT,PULLBACK_MAX_PCT,"%"),minimum("rebound_2m_pct",rebound_2m_pct,REBOUND_2M_PCT,"%")])

            qualifies = (
                not math.isnan(return_30m_pct)
                and not math.isnan(r2_30m)
                and return_30m_pct >= MIN_RETURN_30M_PCT
                and slope_30m_pct_per_hour > 0
                and r2_30m >= MIN_R2
                and PULLBACK_MIN_PCT <= pullback_pct <= PULLBACK_MAX_PCT
                and rebound_2m_pct >= REBOUND_2M_PCT
            )

            if qualifies:
                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        current_price,
                        TARGET_PCT,
                        STOP_PCT,
                        "trend_pullback",
                        return_30m_pct=return_30m_pct,
                        slope_30m_pct_per_hour=slope_30m_pct_per_hour,
                        r2_30m=r2_30m,
                        pullback_from_10m_high_pct=pullback_pct,
                        rebound_2m_pct=rebound_2m_pct,
                    )
                )

        return out
