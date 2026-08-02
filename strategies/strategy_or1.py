"""Snapshot-native OR1 opening-range breakout strategy."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import math
from zoneinfo import ZoneInfo

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .snapshot_common import make_signal


STRATEGY_ID = "OR1"
PAPER_ONLY = True

OR1_BREAK_BUFFER_PCT = 0.10
OR1_ENTRY_END_MINUTE_ET = 10 * 60 + 15
OR1_MAX_RANGE_PCT = 2.50
OR1_MIN_RANGE_PCT = 0.20
OR1_RANGE_END_MINUTE_ET = 9 * 60 + 45

MIN_OPENING_MINUTES = 10


@dataclass
class _OpeningState:
    prices: list[float] = field(default_factory=list)
    minute_keys: set[tuple[int, int]] = field(default_factory=set)


class OR1Strategy(EventStrategy):

    name = STRATEGY_ID

    def __init__(self):
        self._session_date = None
        self._opening = defaultdict(_OpeningState)

    def on_snapshot(
        self,
        snapshot: MarketSnapshot,
    ) -> list[SignalEvent]:

        out = []

        timestamp_et = snapshot.timestamp.astimezone(
            ZoneInfo("America/New_York")
        )
        session_date = timestamp_et.date()
        minute_et = timestamp_et.hour * 60 + timestamp_et.minute

        if session_date != self._session_date:
            self._session_date = session_date
            self._opening.clear()

        is_opening_range = (
            timestamp_et.hour == 9
            and 30 <= timestamp_et.minute < 45
        )

        if is_opening_range:
            minute_key = (
                timestamp_et.hour,
                timestamp_et.minute,
            )

            for symbol, quote in snapshot.quotes.items():
                state = self._opening[symbol]
                state.prices.append(float(quote.price))
                state.minute_keys.add(minute_key)

            return out

        if not (
            OR1_RANGE_END_MINUTE_ET
            <= minute_et
            <= OR1_ENTRY_END_MINUTE_ET
        ):
            return out

        for symbol, quote in snapshot.quotes.items():
            state = self._opening.get(symbol)

            if (
                state is None
                or len(state.minute_keys) < MIN_OPENING_MINUTES
                or not state.prices
            ):
                continue

            opening_high = max(state.prices)
            opening_low = min(state.prices)
            current_price = float(quote.price)

            opening_range_pct = (
                (opening_high / opening_low - 1.0) * 100.0
                if opening_low > 0
                else math.nan
            )

            breakout_pct = (
                (current_price / opening_high - 1.0) * 100.0
                if opening_high > 0
                else math.nan
            )

            if (
                OR1_MIN_RANGE_PCT
                <= opening_range_pct
                <= OR1_MAX_RANGE_PCT
                and breakout_pct >= OR1_BREAK_BUFFER_PCT
            ):
                stop_pct = max(
                    0.50,
                    min(1.00, opening_range_pct * 0.50),
                )
                target_pct = max(
                    0.75,
                    min(1.50, opening_range_pct),
                )

                out.append(
                    make_signal(
                        snapshot,
                        STRATEGY_ID,
                        symbol,
                        current_price,
                        target_pct,
                        stop_pct,
                        "opening_range_breakout",
                        opening_range_high=opening_high,
                        opening_range_low=opening_low,
                        opening_range_pct=opening_range_pct,
                        breakout_pct=breakout_pct,
                    )
                )

        return out
