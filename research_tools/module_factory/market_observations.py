"""
Provider-independent market observations for Module Factory.

Raw provider records are translated here before entering the
research system. Scientists should reason about market information,
not Schwab CSV column names.

This layer intentionally represents what was OBSERVED at a sampling
instant. It does not pretend that minute snapshots are a complete
trade tape or full order book.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping


def _float(value) -> float:
    try:
        if value is None or value == "":
            return math.nan
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _int(value) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _bool(value) -> bool | None:
    if value is None or value == "":
        return None

    text = str(value).strip().lower()

    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False

    return None


def _timestamp_ms(iso_value: str | None) -> int | None:
    if not iso_value:
        return None

    try:
        value = iso_value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)
        return int(dt.timestamp() * 1000)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class MarketObservation:
    market_minute_utc: str
    observed_at_utc: str
    symbol: str

    price: float
    last: float
    mark: float
    bid: float
    ask: float

    last_size: float
    bid_size: float
    ask_size: float

    quote_time_ms: int | None
    trade_time_ms: int | None
    bid_time_ms: int | None
    ask_time_ms: int | None

    regular_last: float
    regular_trade_time_ms: int | None
    extended_last: float

    last_mic: str
    bid_mic: str
    ask_mic: str

    realtime: bool | None

    @property
    def observed_at_ms(self) -> int | None:
        return _timestamp_ms(
            self.observed_at_utc
        )


def from_schwab_row(
    row: Mapping[str, str],
) -> MarketObservation:
    """
    Translate one existing Schwab minute-snapshot CSV row into
    provider-independent research vocabulary.
    """

    return MarketObservation(
        market_minute_utc=row.get(
            "market_minute_utc",
            "",
        ),
        observed_at_utc=row.get(
            "observed_at_utc",
            "",
        ),
        symbol=row.get("symbol", ""),
        price=_float(
            row.get("legacy_price")
        ),
        last=_float(row.get("last")),
        mark=_float(row.get("mark")),
        bid=_float(row.get("bid")),
        ask=_float(row.get("ask")),
        last_size=_float(
            row.get("last_size_raw")
        ),
        bid_size=_float(
            row.get("bid_size_raw")
        ),
        ask_size=_float(
            row.get("ask_size_raw")
        ),
        quote_time_ms=_int(
            row.get("quote_time_ms")
        ),
        trade_time_ms=_int(
            row.get("trade_time_ms")
        ),
        bid_time_ms=_int(
            row.get("bid_time_ms")
        ),
        ask_time_ms=_int(
            row.get("ask_time_ms")
        ),
        regular_last=_float(
            row.get("regular_last")
        ),
        regular_trade_time_ms=_int(
            row.get(
                "regular_trade_time_ms"
            )
        ),
        extended_last=_float(
            row.get("extended_last")
        ),
        last_mic=row.get(
            "last_mic",
            "",
        ),
        bid_mic=row.get(
            "bid_mic",
            "",
        ),
        ask_mic=row.get(
            "ask_mic",
            "",
        ),
        realtime=_bool(
            row.get("realtime")
        ),
    )
