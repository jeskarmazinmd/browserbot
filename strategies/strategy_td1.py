"""Snapshot-native TD1 time-of-day relative-strength strategy."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta
import math
from zoneinfo import ZoneInfo

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .snapshot_common import (
    Observation,
    make_signal,
    trim_before,
    value_at_or_before,
)


STRATEGY_ID = "TD1"
PAPER_ONLY = True

NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"
TD1_END_MINUTE_ET = 11 * 60 + 30
TD1_MIN_EXCESS_VS_SPY_PCT = 0.50
TD1_MIN_RETURN_30M_PCT = 0.60
TD1_START_MINUTE_ET = 10 * 60

LOOKBACK_MINUTES = 30
TARGET_PCT = 0.75
STOP_PCT = 0.55


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


class TD1Strategy(EventStrategy):

    name = STRATEGY_ID

    def __init__(self):
        self._state = defaultdict(_State)

    def on_snapshot(
        self,
        snapshot: MarketSnapshot,
    ) -> list[SignalEvent]:

        out = []

        # Update every history first so stock and SPY returns use one timestamp.
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

        timestamp_et = snapshot.timestamp.astimezone(
            ZoneInfo("America/New_York")
        )
        minute_et = timestamp_et.hour * 60 + timestamp_et.minute

        if not (
            TD1_START_MINUTE_ET
            <= minute_et
            <= TD1_END_MINUTE_ET
        ):
            return out

        spy_state = self._state.get("SPY")

        if spy_state is None:
            return out

        spy_prices = _minute_prices(
            spy_state.observations,
            snapshot.timestamp,
        )

        if spy_prices is None:
            return out

        spy_return_30m_pct = _simple_return_pct(
            spy_prices[0],
            spy_prices[-1],
        )

        if math.isnan(spy_return_30m_pct):
            return out

        for symbol, quote in snapshot.quotes.items():
            if symbol == "SPY":
                continue

            prices = _minute_prices(
                self._state[symbol].observations,
                snapshot.timestamp,
            )

            if prices is None:
                continue

            ret30 = _simple_return_pct(
                prices[0],
                prices[-1],
            )
            ret5 = _simple_return_pct(
                prices[-6],
                prices[-1],
            )
            excess = ret30 - spy_return_30m_pct

            if (
                ret30 >= TD1_MIN_RETURN_30M_PCT
                and excess >= TD1_MIN_EXCESS_VS_SPY_PCT
                and ret5 > 0
            ):
                current_price = float(quote.price)

                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        current_price,
                        TARGET_PCT,
                        STOP_PCT,
                        "time_of_day_relative_strength",
                        minute_et=minute_et,
                        return_30m_pct=ret30,
                        spy_return_30m_pct=spy_return_30m_pct,
                        excess_return_30m_pct=excess,
                        return_5m_pct=ret5,
                        forward_start_utc=(
                            NEW_RESEARCH_FORWARD_START_UTC
                        ),
                    )
                )

        return out
