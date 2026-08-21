"""Snapshot-native RS1 relative strength strategy."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta
import math

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .snapshot_common import Observation, make_signal, prices_since, trim_before
from .nearest_miss import consider, minimum, reset


STRATEGY_ID = "RS1"
PAPER_ONLY = True

RS1_MIN_EXCESS_VS_SPY_PCT = 0.75
RS1_MIN_R2 = 0.50
RS1_MIN_RETURN_30M_PCT = 0.75

TARGET_PCT = 0.90
STOP_PCT = 0.65


@dataclass
class _State:
    observations: deque[Observation] = field(default_factory=deque)


def _simple_return_pct(old_price: float, new_price: float) -> float:
    if old_price <= 0:
        return math.nan
    return (new_price / old_price - 1.0) * 100.0


def _fit_log_slope_r2(prices: list[float]) -> tuple[float, float]:
    if len(prices) < 2:
        return math.nan, math.nan

    logs = [math.log(p) for p in prices if p > 0]

    if len(logs) < 2:
        return math.nan, math.nan

    x = list(range(len(logs)))

    x_mean = sum(x) / len(x)
    y_mean = sum(logs) / len(logs)

    denominator = sum((v - x_mean) ** 2 for v in x)

    if denominator == 0:
        return math.nan, math.nan

    slope = sum(
        (a - x_mean) * (b - y_mean)
        for a, b in zip(x, logs)
    ) / denominator

    fitted = [
        y_mean + slope * (a - x_mean)
        for a in x
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


def _return_30m(observations: deque[Observation], timestamp):
    prices = prices_since(
        observations,
        timestamp - timedelta(minutes=30),
    )

    if len(prices) < 31:
        return math.nan, []

    return _simple_return_pct(prices[0], prices[-1]), prices


class RS1Strategy(EventStrategy):

    name = STRATEGY_ID

    def __init__(self):
        self._state = defaultdict(_State)

    def on_snapshot(
        self,
        snapshot: MarketSnapshot,
    ) -> list[SignalEvent]:

        out = []
        reset(self)

        # update all symbol histories first
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
                snapshot.timestamp - timedelta(minutes=60),
            )

        spy_state = self._state.get("SPY")

        if spy_state is None:
            return out

        spy_return, _ = _return_30m(
            spy_state.observations,
            snapshot.timestamp,
        )

        if math.isnan(spy_return):
            return out

        for symbol, quote in snapshot.quotes.items():

            if symbol == "SPY":
                continue

            state = self._state[symbol]

            ret30, prices = _return_30m(
                state.observations,
                snapshot.timestamp,
            )

            if len(prices) < 31 or math.isnan(ret30):
                continue

            _, r2_30 = _fit_log_slope_r2(prices)

            excess = ret30 - spy_return

            consider(self, symbol, snapshot.timestamp, float(quote.price), [minimum("return_30m_pct", ret30, RS1_MIN_RETURN_30M_PCT, "%"), minimum("excess_vs_spy_pct", excess, RS1_MIN_EXCESS_VS_SPY_PCT, "%"), minimum("r2_30m", r2_30, RS1_MIN_R2)])

            if (
                ret30 >= RS1_MIN_RETURN_30M_PCT
                and excess >= RS1_MIN_EXCESS_VS_SPY_PCT
                and r2_30 >= RS1_MIN_R2
            ):
                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        float(quote.price),
                        TARGET_PCT,
                        STOP_PCT,
                        "relative_strength",
                        return_30m_pct=ret30,
                        spy_return_30m_pct=spy_return,
                        excess_return_30m_pct=excess,
                        r2_30m=r2_30,
                    )
                )

        return out
