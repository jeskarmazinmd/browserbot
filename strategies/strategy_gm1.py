"""Snapshot-native GM1 generic mean-reversion strategy."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta

from detectors.mean_reversion import detect_mean_reversion
from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .nearest_miss import consider, maximum, minimum, reset
from .snapshot_common import (
    Observation,
    make_signal,
    trim_before,
    value_at_or_before,
)


STRATEGY_ID = "GM1"
PAPER_ONLY = True

BASELINE_WINDOW = 30
RECENT_WINDOW = 5
MAX_ZSCORE = -1.25
MIN_REBOUND_FROM_RECENT_LOW_PCT = 0.10

TARGET_PCT = 0.65
STOP_PCT = 0.80


@dataclass
class _State:
    observations: deque[Observation] = field(default_factory=deque)


def _minute_prices(
    observations: deque[Observation],
    timestamp,
) -> list[float] | None:

    window_start = timestamp - timedelta(minutes=BASELINE_WINDOW)

    if (
        not observations
        or observations[0].timestamp > window_start
    ):
        return None

    prices = []

    for minutes_ago in range(BASELINE_WINDOW, -1, -1):
        item = value_at_or_before(
            observations,
            timestamp - timedelta(minutes=minutes_ago),
        )

        if item is None:
            return None

        prices.append(float(item.price))

    return prices


class GM1Strategy(EventStrategy):

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
                - timedelta(minutes=BASELINE_WINDOW + 5),
            )

            prices = _minute_prices(
                state.observations,
                snapshot.timestamp,
            )

            if prices is None:
                continue

            detection = detect_mean_reversion(
                prices,
                baseline_window=BASELINE_WINDOW,
                recent_window=RECENT_WINDOW,
            )

            if not detection.get("detected"):
                continue

            consider(self, symbol, snapshot.timestamp, float(quote.price), [maximum("zscore", detection["zscore"], MAX_ZSCORE), minimum("rebound_from_recent_low_pct", detection["rebound_from_recent_low_pct"], MIN_REBOUND_FROM_RECENT_LOW_PCT, "%")])

            if (
                detection["zscore"] > MAX_ZSCORE
                or (
                    detection["rebound_from_recent_low_pct"]
                    < MIN_REBOUND_FROM_RECENT_LOW_PCT
                )
            ):
                continue

            metrics = {
                f"reversion_{key}": value
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
                    "generic_mean_reversion",
                    **metrics,
                )
            )

        return out
