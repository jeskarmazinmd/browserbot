"""Snapshot-native GP1 generic trend-pullback strategy."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta

from detectors.pullback import detect_pullback
from detectors.trend import detect_trend
from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .snapshot_common import (
    Observation,
    make_signal,
    trim_before,
    value_at_or_before,
)


STRATEGY_ID = "GP1"
PAPER_ONLY = True

TREND_WINDOW = 30
MIN_TREND_RETURN_PCT = 0.50
MIN_TREND_R2 = 0.25
MIN_PULLBACK_DEPTH_PCT = 0.20
MAX_PULLBACK_DEPTH_PCT = 1.50
MIN_RECOVERY_FROM_LOW_PCT = 0.10

TARGET_PCT = 0.65
STOP_PCT = 0.65


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


class GP1Strategy(EventStrategy):

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
                - timedelta(minutes=TREND_WINDOW + 5),
            )

            prices = _minute_prices(
                state.observations,
                snapshot.timestamp,
            )

            if prices is None:
                continue

            trend = detect_trend(
                prices,
                window=TREND_WINDOW,
            )
            pullback = detect_pullback(
                prices,
                trend_window=TREND_WINDOW,
            )

            if (
                not trend.get("detected")
                or not pullback.get("detected")
            ):
                continue

            if (
                trend["return_pct"] < MIN_TREND_RETURN_PCT
                or trend["r2"] < MIN_TREND_R2
            ):
                continue

            if not (
                MIN_PULLBACK_DEPTH_PCT
                <= pullback["pullback_depth_pct"]
                <= MAX_PULLBACK_DEPTH_PCT
            ):
                continue

            if (
                pullback["recovery_from_low_pct"]
                < MIN_RECOVERY_FROM_LOW_PCT
            ):
                continue

            metrics = {
                **{
                    f"trend_{key}": value
                    for key, value in trend.items()
                },
                **{
                    f"pullback_{key}": value
                    for key, value in pullback.items()
                },
            }

            out.append(
                make_signal(
                    snapshot,
                    STRATEGY_ID,
                    symbol,
                    float(quote.price),
                    TARGET_PCT,
                    STOP_PCT,
                    "generic_trend_pullback",
                    **metrics,
                )
            )

        return out
