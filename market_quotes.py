"""Normalized Schwab quote extraction without execution assumptions."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    legacy_price: float | None
    last: float | None
    mark: float | None
    bid: float | None
    ask: float | None
    last_size_raw: float | None
    bid_size_raw: float | None
    ask_size_raw: float | None
    quote_time_ms: int | None
    trade_time_ms: int | None
    bid_time_ms: int | None
    ask_time_ms: int | None
    regular_last: float | None
    regular_trade_time_ms: int | None
    extended_last: float | None
    last_mic: str | None
    bid_mic: str | None
    ask_mic: str | None
    realtime: bool | None

    def as_dict(self):
        return asdict(self)


def _number(value, positive=False):
    try:
        result=float(value)
    except (TypeError,ValueError):
        return None
    if positive and result <= 0:
        return None
    return result


def _integer(value):
    try:
        return int(value)
    except (TypeError,ValueError):
        return None


def _mapping(value):
    return value if isinstance(value,Mapping) else {}


def legacy_scalar_price(payload):
    """Exactly preserve the pre-migration scalar-price fallback ordering."""
    if not isinstance(payload,Mapping):
        return None

    containers=[payload]
    for key in ("quote","regular","extended","reference"):
        child=payload.get(key)
        if isinstance(child,Mapping):
            containers.append(child)

    for obj in containers:
        for key in (
            "lastPrice",
            "mark",
            "regularMarketLastPrice",
            "closePrice",
            "bidPrice",
            "askPrice",
        ):
            value=_number(obj.get(key),positive=True)
            if value is not None:
                return value

    return None


def extract_quote_snapshot(symbol,payload):
    """Preserve distinct observed quote fields for execution/research use."""
    root=_mapping(payload)
    quote=_mapping(root.get("quote"))
    regular=_mapping(root.get("regular"))
    extended=_mapping(root.get("extended"))

    return QuoteSnapshot(
        symbol=str(symbol).upper(),
        legacy_price=legacy_scalar_price(root),
        last=_number(quote.get("lastPrice"),True),
        mark=_number(quote.get("mark"),True),
        bid=_number(quote.get("bidPrice"),True),
        ask=_number(quote.get("askPrice"),True),
        last_size_raw=_number(quote.get("lastSize")),
        bid_size_raw=_number(quote.get("bidSize")),
        ask_size_raw=_number(quote.get("askSize")),
        quote_time_ms=_integer(quote.get("quoteTime")),
        trade_time_ms=_integer(quote.get("tradeTime")),
        bid_time_ms=_integer(quote.get("bidTime")),
        ask_time_ms=_integer(quote.get("askTime")),
        regular_last=_number(regular.get("regularMarketLastPrice"),True),
        regular_trade_time_ms=_integer(regular.get("regularMarketTradeTime")),
        extended_last=_number(extended.get("lastPrice"),True),
        last_mic=quote.get("lastMICId"),
        bid_mic=quote.get("bidMICId"),
        ask_mic=quote.get("askMICId"),
        realtime=bool(root["realtime"]) if root.get("realtime") is not None else None,
    )
