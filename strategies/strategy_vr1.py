"""Snapshot-native VR1 rolling-mean reclaim strategy."""

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
    time_weighted_mean,
    trim_before,
    value_at_or_before,
)


STRATEGY_ID = "VR1"
PAPER_ONLY = True

VR1_HOLD_MINUTES = 2
VR1_MIN_DEPTH_BELOW_VWAP_PCT = 0.40

TARGET_PCT = 0.75
STOP_PCT = 0.45


@dataclass
class _State:
    observations: deque[Observation] = field(default_factory=deque)


class VR1Strategy(EventStrategy):

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
                snapshot.timestamp - timedelta(minutes=35),
            )

            window_start = snapshot.timestamp - timedelta(minutes=30)
            two_minutes_ago = snapshot.timestamp - timedelta(minutes=2)
            one_minute_ago = snapshot.timestamp - timedelta(minutes=1)

            start_observation = value_at_or_before(
                state.observations,
                window_start,
            )
            prior_two = value_at_or_before(
                state.observations,
                two_minutes_ago,
            )
            prior_one = value_at_or_before(
                state.observations,
                one_minute_ago,
            )

            if (
                start_observation is None
                or prior_two is None
                or prior_one is None
            ):
                continue

            # At one-minute cadence this equals the legacy mean of the
            # first 29 values in the trailing 31-minute series.
            proxy = time_weighted_mean(
                state.observations,
                window_start,
                one_minute_ago,
            )

            if proxy is None:
                continue

            historical_prices = [start_observation.price]
            historical_prices.extend(
                item.price
                for item in state.observations
                if (
                    window_start < item.timestamp <= two_minutes_ago
                )
            )

            historical_low = min(historical_prices)

            depth_pct = (
                (proxy / historical_low - 1.0) * 100.0
                if historical_low > 0
                else math.nan
            )

            current_price = float(quote.price)

            held_above = (
                prior_one.price >= proxy
                and current_price >= proxy
            )
            crossed = (
                prior_two.price < proxy <= prior_one.price
            )

            if (
                depth_pct >= VR1_MIN_DEPTH_BELOW_VWAP_PCT
                and crossed
                and held_above
            ):
                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        current_price,
                        TARGET_PCT,
                        STOP_PCT,
                        "rolling_mean_reclaim_proxy",
                        rolling_mean_30m=proxy,
                        prior_depth_below_proxy_pct=depth_pct,
                        confirmation_minutes=VR1_HOLD_MINUTES,
                    )
                )

        return out
