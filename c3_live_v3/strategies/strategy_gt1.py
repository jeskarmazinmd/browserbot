"""Snapshot-native GT1 generic trend-continuation strategy."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta

from detectors.trend import detect_trend
from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .nearest_miss import consider, minimum, reset
from .snapshot_common import (
    Observation,
    make_signal,
    trim_before,
    value_at_or_before,
)


STRATEGY_ID = "GT1"
PAPER_ONLY = True

TREND_WINDOW = 30
MIN_RETURN_PCT = 0.60
MIN_R2 = 0.35
MIN_UP_MINUTE_FRACTION = 0.52

TARGET_PCT = 0.70
STOP_PCT = 0.70


@dataclass
class _State:
    observations: deque[Observation] = field(default_factory=deque)


def _minute_prices(
    observations: deque[Observation],
    timestamp,
) -> list[float] | None:

    window_start = timestamp - timedelta(minutes=TREND_WINDOW)

    if (
        not observations
        or observations[0].timestamp > window_start
    ):
        return None

    prices = []

    for minutes_ago in range(TREND_WINDOW, -1, -1):
        item = value_at_or_before(
            observations,
            timestamp - timedelta(minutes=minutes_ago),
        )

        if item is None:
            return None

        prices.append(float(item.price))

    return prices


class GT1Strategy(EventStrategy):

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
                - timedelta(minutes=TREND_WINDOW + 5),
            )

            prices = _minute_prices(
                state.observations,
                snapshot.timestamp,
            )

            if prices is None:
                continue

            detection = detect_trend(
                prices,
                window=TREND_WINDOW,
            )

            if not detection.get("detected"):
                continue

            consider(self, symbol, snapshot.timestamp, float(quote.price), [minimum("return_pct", detection["return_pct"], MIN_RETURN_PCT, "%"), minimum("r2", detection["r2"], MIN_R2), minimum("up_minute_fraction", detection["up_minute_fraction"], MIN_UP_MINUTE_FRACTION)])

            if (
                detection["return_pct"] < MIN_RETURN_PCT
                or detection["r2"] < MIN_R2
                or (
                    detection["up_minute_fraction"]
                    < MIN_UP_MINUTE_FRACTION
                )
            ):
                continue

            metrics = {
                f"trend_{key}": value
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
                    "generic_trend_continuation",
                    **metrics,
                )
            )

        return out
