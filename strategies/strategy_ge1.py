"""Snapshot-native GE1 generic selling-exhaustion strategy."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta

from detectors.exhaustion import detect_selling_exhaustion
from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .snapshot_common import (
    Observation,
    make_signal,
    trim_before,
    value_at_or_before,
)


STRATEGY_ID = "GE1"
PAPER_ONLY = True

LOOKBACK_MINUTES = 12
MIN_DECLINE_TO_LOW_PCT = 0.60
MIN_REBOUND_FROM_LOW_PCT = 0.10
MIN_EXHAUSTION_SCORE = 0.35

TARGET_PCT = 0.60
STOP_PCT = 0.75


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


class GE1Strategy(EventStrategy):

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

            detection = detect_selling_exhaustion(
                prices,
                window=LOOKBACK_MINUTES,
            )

            if not detection.get("detected"):
                continue

            if (
                detection["decline_to_low_pct"]
                < MIN_DECLINE_TO_LOW_PCT
                or detection["rebound_from_low_pct"]
                < MIN_REBOUND_FROM_LOW_PCT
                or detection["score"] < MIN_EXHAUSTION_SCORE
            ):
                continue

            metrics = {
                f"exhaustion_{key}": value
                for key, value in detection.items()
            }

            out.append(
                make_signal(
                    snapshot,
                    STRATEGY_ID,
                    symbol,
                    float(quote.price),
                    TARGET_PCT,
                    STOP_PCT,
                    "generic_selling_exhaustion",
                    **metrics,
                )
            )

        return out
