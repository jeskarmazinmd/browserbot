"""Snapshot-native VE1 volatility-expansion strategy."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta
import math

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .nearest_miss import consider, maximum, minimum, reset
from .snapshot_common import Observation, make_signal, trim_before


STRATEGY_ID = "VE1"
PAPER_ONLY = True

VE1_BREAK_BUFFER_PCT = 0.10
VE1_COMPRESSION_MINUTES = 15
VE1_MAX_COMPRESSION_RANGE_PCT = 0.60

STOP_PCT = 0.60


@dataclass
class _State:
    observations: deque[Observation] = field(default_factory=deque)


class VE1Strategy(EventStrategy):

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
                snapshot.timestamp - timedelta(minutes=20),
            )

            # Require the same history coverage as 17 one-minute observations.
            coverage_start = snapshot.timestamp - timedelta(
                minutes=VE1_COMPRESSION_MINUTES + 1,
            )

            if state.observations[0].timestamp > coverage_start:
                continue

            # Measure the preceding 15 minutes, excluding the current snapshot.
            window_start = snapshot.timestamp - timedelta(
                minutes=VE1_COMPRESSION_MINUTES,
            )

            compressed = [
                item.price
                for item in state.observations
                if window_start <= item.timestamp < snapshot.timestamp
            ]

            if not compressed:
                continue

            c_high = max(compressed)
            c_low = min(compressed)
            price = float(quote.price)

            c_range_pct = (
                (c_high / c_low - 1.0) * 100.0
                if c_low > 0
                else math.nan
            )

            expansion_pct = (
                (price / c_high - 1.0) * 100.0
                if c_high > 0
                else math.nan
            )

            consider(self,symbol,snapshot.timestamp,price,[maximum("compression_range_pct",c_range_pct,VE1_MAX_COMPRESSION_RANGE_PCT,"%"),minimum("expansion_pct",expansion_pct,VE1_BREAK_BUFFER_PCT,"%")])

            if (
                c_range_pct <= VE1_MAX_COMPRESSION_RANGE_PCT
                and expansion_pct >= VE1_BREAK_BUFFER_PCT
            ):
                target_pct = max(
                    0.60,
                    min(1.20, c_range_pct * 1.5),
                )

                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        price,
                        target_pct,
                        STOP_PCT,
                        "volatility_expansion",
                        compression_range_high=c_high,
                        compression_range_low=c_low,
                        compression_range_pct=c_range_pct,
                        expansion_pct=expansion_pct,
                    )
                )

        return out
