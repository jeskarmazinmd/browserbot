"""Snapshot-native SH1 decline-shape flattening strategy."""

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


STRATEGY_ID = "SH1"
PAPER_ONLY = True

NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"
SH1_MIN_DECLINE_20M_PCT = 1.00
SH1_MIN_FLATTENING_RATIO = 0.50

LOOKBACK_MINUTES = 20
TARGET_PCT = 0.70
STOP_PCT = 0.60


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


class SH1Strategy(EventStrategy):

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

            current_price = float(quote.price)
            low_price = min(prices)

            decline20 = (
                (prices[0] / low_price - 1.0) * 100.0
                if low_price > 0
                else math.nan
            )

            first_half = _simple_return_pct(
                prices[0],
                prices[10],
            )
            second_half = _simple_return_pct(
                prices[10],
                prices[-1],
            )
            rebound3 = _simple_return_pct(
                prices[-4],
                prices[-1],
            )

            flattening = (
                abs(second_half) / abs(first_half)
                if first_half < 0
                else math.inf
            )

            if (
                decline20 >= SH1_MIN_DECLINE_20M_PCT
                and first_half < 0
                and flattening <= SH1_MIN_FLATTENING_RATIO
                and rebound3 > 0
            ):
                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        current_price,
                        TARGET_PCT,
                        STOP_PCT,
                        "decline_shape_flattening",
                        decline_20m_pct=decline20,
                        first_half_return_pct=first_half,
                        second_half_return_pct=second_half,
                        flattening_ratio=flattening,
                        rebound_3m_pct=rebound3,
                        forward_start_utc=(
                            NEW_RESEARCH_FORWARD_START_UTC
                        ),
                    )
                )

        return out
