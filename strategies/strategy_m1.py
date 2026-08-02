"""Snapshot-native M1 medium-reversal strategy."""

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


STRATEGY_ID = "M1"
PAPER_ONLY = True

LOOKBACK_MINUTES = 15
MIN_DECLINE_PCT = 1.50
MIN_REBOUND_FROM_LOW_PCT = 0.25
MIN_REBOUND_2M_PCT = 0.10
TARGET_PCT = 0.75
STOP_PCT = 0.75

MEDIUM_REVERSAL_MAX_LOW_AGE_MINUTES = 10
MEDIUM_REVERSAL_MAX_SINGLE_MINUTE_SHARE = 0.75
MEDIUM_REVERSAL_MIN_LOW_AGE_MINUTES = 2


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


class M1Strategy(EventStrategy):

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

            start_price = prices[0]
            low_price = min(prices)
            low_index = prices.index(low_price)

            decline_pct = (
                (start_price / low_price - 1.0) * 100.0
                if low_price > 0
                else math.nan
            )

            low_age_minutes = (
                len(prices) - 1 - low_index
            )

            current_price = float(quote.price)

            rebound_from_low_pct = (
                (current_price / low_price - 1.0) * 100.0
                if low_price > 0
                else math.nan
            )

            rebound_2m_pct = _simple_return_pct(
                prices[-3],
                prices[-1],
            )

            one_minute_declines = [
                -_simple_return_pct(previous, current)
                for previous, current in zip(prices, prices[1:])
            ]

            largest_one_minute_decline_pct = max(
                0.0,
                max(one_minute_declines),
            )

            largest_minute_share = (
                largest_one_minute_decline_pct / decline_pct
                if decline_pct > 0
                else math.inf
            )

            prior_minute_above_low = prices[-2] > low_price

            if (
                decline_pct >= MIN_DECLINE_PCT
                and (
                    MEDIUM_REVERSAL_MIN_LOW_AGE_MINUTES
                    <= low_age_minutes
                    <= MEDIUM_REVERSAL_MAX_LOW_AGE_MINUTES
                )
                and rebound_from_low_pct >= MIN_REBOUND_FROM_LOW_PCT
                and rebound_2m_pct >= MIN_REBOUND_2M_PCT
                and prior_minute_above_low
                and (
                    largest_minute_share
                    <= MEDIUM_REVERSAL_MAX_SINGLE_MINUTE_SHARE
                )
            ):
                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        current_price,
                        TARGET_PCT,
                        STOP_PCT,
                        f"medium_reversal_{LOOKBACK_MINUTES}m",
                        lookback_minutes=LOOKBACK_MINUTES,
                        decline_from_window_start_to_low_pct=decline_pct,
                        window_start_price=start_price,
                        window_low_price=low_price,
                        low_age_minutes=low_age_minutes,
                        rebound_from_low_pct=rebound_from_low_pct,
                        rebound_2m_pct=rebound_2m_pct,
                        largest_one_minute_decline_pct=(
                            largest_one_minute_decline_pct
                        ),
                        largest_minute_share_of_decline=(
                            largest_minute_share
                        ),
                    )
                )

        return out
