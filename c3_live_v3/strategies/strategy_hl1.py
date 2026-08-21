"""Snapshot-native HL1 higher-low breakout strategy."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta
import math

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .nearest_miss import consider, minimum, reset
from .snapshot_common import (
    Observation,
    make_signal,
    trim_before,
    value_at_or_before,
)


STRATEGY_ID = "HL1"
PAPER_ONLY = True

HL1_BREAK_BUFFER_PCT = 0.10
HL1_MIN_HIGHER_LOW_PCT = 0.15
NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"

LOOKBACK_MINUTES = 20
TARGET_PCT = 0.80
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


class HL1Strategy(EventStrategy):

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

            local_lows = [
                index
                for index in range(1, len(prices) - 1)
                if (
                    prices[index] <= prices[index - 1]
                    and prices[index] < prices[index + 1]
                )
            ]

            if len(local_lows) < 2:
                continue

            first_index = local_lows[-2]
            second_index = local_lows[-1]

            if second_index - first_index < 3:
                continue

            first_low = prices[first_index]
            second_low = prices[second_index]

            higher_low_pct = (
                (second_low / first_low - 1.0) * 100.0
                if first_low > 0
                else math.nan
            )

            intervening_high = max(
                prices[first_index:second_index + 1]
            )
            current_price = float(quote.price)

            breakout_pct = (
                (current_price / intervening_high - 1.0) * 100.0
                if intervening_high > 0
                else math.nan
            )
            consider(self,symbol,snapshot.timestamp,current_price,[minimum("higher_low_pct",higher_low_pct,HL1_MIN_HIGHER_LOW_PCT,"%"),minimum("breakout_pct",breakout_pct,HL1_BREAK_BUFFER_PCT,"%")])

            if (
                higher_low_pct >= HL1_MIN_HIGHER_LOW_PCT
                and breakout_pct >= HL1_BREAK_BUFFER_PCT
            ):
                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        current_price,
                        TARGET_PCT,
                        STOP_PCT,
                        "higher_low_breakout",
                        first_low=first_low,
                        second_low=second_low,
                        higher_low_pct=higher_low_pct,
                        intervening_high=intervening_high,
                        breakout_pct=breakout_pct,
                        forward_start_utc=(
                            NEW_RESEARCH_FORWARD_START_UTC
                        ),
                    )
                )

        return out
