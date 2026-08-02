"""Snapshot-native GR1 generic support-rejection strategy."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta

from detectors.rejection import detect_support_rejection
from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .snapshot_common import (
    Observation,
    make_signal,
    trim_before,
    value_at_or_before,
)


STRATEGY_ID = "GR1"
PAPER_ONLY = True

DETECTOR_WINDOW = 20
LOOKBACK_MINUTES = DETECTOR_WINDOW - 1
SUPPORT_TOLERANCE_PCT = 0.20
MIN_CONFIRMATION_FROM_SUPPORT_PCT = 0.12
MIN_SEPARATION_BOUNCE_PCT = 0.15

TARGET_PCT = 0.60


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


class GR1Strategy(EventStrategy):

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

            detection = detect_support_rejection(
                prices,
                window=DETECTOR_WINDOW,
                tolerance_pct=SUPPORT_TOLERANCE_PCT,
            )

            if not detection.get("detected"):
                continue

            if (
                detection["confirmation_from_support_pct"]
                < MIN_CONFIRMATION_FROM_SUPPORT_PCT
                or detection["separation_bounce_pct"]
                < MIN_SEPARATION_BOUNCE_PCT
            ):
                continue

            stop_pct = max(
                0.35,
                min(
                    1.00,
                    detection["confirmation_from_support_pct"]
                    + 0.15,
                ),
            )

            metrics = {
                f"rejection_{key}": value
                for key, value in detection.items()
            }

            out.append(
                make_signal(
                    snapshot,
                    STRATEGY_ID,
                    symbol,
                    float(quote.price),
                    TARGET_PCT,
                    stop_pct,
                    "generic_support_rejection",
                    **metrics,
                )
            )

        return out
