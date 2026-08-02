"""Snapshot-native PD1 panic-drop snapback strategy."""

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


STRATEGY_ID = "PD1"
PAPER_ONLY = True

NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"
PD1_MIN_ONE_MINUTE_DROP_PCT = 1.00
PD1_MIN_REBOUND_FROM_LOW_PCT = 0.40

LOOKBACK_MINUTES = 11
TARGET_PCT = 0.85
STOP_PCT = 0.70


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


class PD1Strategy(EventStrategy):

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

            minute_returns = [
                _simple_return_pct(previous, current)
                for previous, current in zip(prices, prices[1:])
            ]

            worst_return_index = min(
                range(len(minute_returns)),
                key=minute_returns.__getitem__,
            )

            # pct_change index labels start at 1 in the legacy DataFrame.
            worst_position = worst_return_index + 1
            worst_drop = -minute_returns[worst_return_index]

            subsequent_prices = prices[worst_position:]
            low_after = min(subsequent_prices)
            low_position = (
                worst_position
                + subsequent_prices.index(low_after)
            )

            low_age = len(prices) - 1 - low_position
            current_price = float(quote.price)

            rebound_low = (
                (current_price / low_after - 1.0) * 100.0
                if low_after > 0
                else math.nan
            )

            rebound2 = _simple_return_pct(
                prices[-3],
                prices[-1],
            )

            if (
                worst_drop >= PD1_MIN_ONE_MINUTE_DROP_PCT
                and 2 <= low_age <= 8
                and rebound_low >= PD1_MIN_REBOUND_FROM_LOW_PCT
                and rebound2 > 0
            ):
                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        current_price,
                        TARGET_PCT,
                        STOP_PCT,
                        "panic_drop_snapback",
                        worst_one_minute_drop_pct=worst_drop,
                        low_age_minutes=low_age,
                        rebound_from_low_pct=rebound_low,
                        rebound_2m_pct=rebound2,
                        forward_start_utc=(
                            NEW_RESEARCH_FORWARD_START_UTC
                        ),
                    )
                )

        return out
