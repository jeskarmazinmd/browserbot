"""Snapshot-native BO1 consolidation-breakout strategy."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta
import math

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .snapshot_common import Observation, make_signal, trim_before


STRATEGY_ID = "BO1"
PAPER_ONLY = True

BO1_BREAK_BUFFER_PCT = 0.10
BO1_LOOKBACK_MINUTES = 10
BO1_MAX_RANGE_PCT = 0.75

TARGET_PCT = 1.00
STOP_PCT = 0.75


@dataclass
class _State:
    observations: deque[Observation] = field(default_factory=deque)


class BO1Strategy(EventStrategy):

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
                snapshot.timestamp - timedelta(minutes=15),
            )

            # The legacy rule required 12 minute observations and measured
            # the 10 preceding minutes, excluding the current price.
            coverage_start = snapshot.timestamp - timedelta(
                minutes=BO1_LOOKBACK_MINUTES + 1,
            )

            if state.observations[0].timestamp > coverage_start:
                continue

            window_start = snapshot.timestamp - timedelta(
                minutes=BO1_LOOKBACK_MINUTES,
            )

            prior_prices = [
                item.price
                for item in state.observations
                if window_start <= item.timestamp < snapshot.timestamp
            ]

            if not prior_prices:
                continue

            prior_high = max(prior_prices)
            prior_low = min(prior_prices)
            current_price = float(quote.price)

            range_pct = (
                (prior_high / prior_low - 1.0) * 100.0
                if prior_low > 0
                else math.nan
            )

            breakout_pct = (
                (current_price / prior_high - 1.0) * 100.0
                if prior_high > 0
                else math.nan
            )

            if (
                range_pct <= BO1_MAX_RANGE_PCT
                and breakout_pct >= BO1_BREAK_BUFFER_PCT
            ):
                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        current_price,
                        TARGET_PCT,
                        STOP_PCT,
                        "consolidation_breakout",
                        prior_range_high=prior_high,
                        prior_range_low=prior_low,
                        prior_range_pct=range_pct,
                        breakout_pct=breakout_pct,
                    )
                )

        return out
