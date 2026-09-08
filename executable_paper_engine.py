"""Shared realistic bid/ask paper-execution primitives.

This module NEVER places broker orders.

Long positions:
- enter at executable ASK
- mark/exit at executable BID
- enforce quote freshness
- enforce displayed ask liquidity
- distinguish FULL / PARTIAL / ZERO / UNKNOWN

UNKNOWN means the available market data cannot support a fill/no-fill claim.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
import math


EXECUTION_MODEL = "BIDASK_EXEC_V1"


def _number(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _positive(value: Any) -> float | None:
    value = _number(value)
    return value if value is not None and value > 0 else None


def _utc(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)

    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def _quote_age_ms(
    quote: Mapping[str, Any],
    now: datetime,
    *,
    side: str,
) -> float | None:
    # For a long entry ASK freshness is controlling.
    # For a long liquidation BID freshness is controlling.
    if side == "ASK":
        timestamp = (
            _number(quote.get("ask_time_ms"))
            or _number(quote.get("quote_time_ms"))
        )
        precalculated = (
            _number(quote.get("ask_age_seconds"))
            or _number(quote.get("age_seconds"))
        )
    else:
        timestamp = (
            _number(quote.get("bid_time_ms"))
            or _number(quote.get("quote_time_ms"))
        )
        precalculated = (
            _number(quote.get("bid_age_seconds"))
            or _number(quote.get("age_seconds"))
        )

    if timestamp is not None and timestamp > 0:
        return now.timestamp() * 1000.0 - timestamp

    if precalculated is not None:
        return precalculated * 1000.0

    return None


@dataclass(frozen=True)
class ExecutionDecision:
    outcome: str
    reason: str
    bid: float | None
    ask: float | None
    requested_qty: int
    filled_qty: int | None
    fill_price: float | None
    quote_age_ms: float | None
    displayed_qty: int | None
    limit_price: float

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result.update(
            execution_model=EXECUTION_MODEL,
            entry_price_source="ASK",
            exit_price_source="BID",
            quote_freshness_enforced=True,
            liquidity_checked=True,
        )
        return result


def classify_long_limit(
    quote: Mapping[str, Any] | None,
    *,
    limit_price: float,
    requested_qty: int,
    now: datetime | str | None = None,
    max_quote_age_ms: float = 2000.0,
    ask_size_multiplier: float = 1.0,
    require_trade_through: bool = False,
) -> ExecutionDecision:
    """Classify a prospective long fill from top-of-book evidence."""

    now = _utc(now)
    quote = quote or {}

    bid = _positive(quote.get("bid"))
    ask = _positive(quote.get("ask"))

    try:
        requested_qty = int(requested_qty)
    except (TypeError, ValueError):
        requested_qty = 0

    limit = _positive(limit_price) or 0.0

    base = dict(
        bid=bid,
        ask=ask,
        requested_qty=requested_qty,
        limit_price=limit,
    )

    if requested_qty <= 0 or limit <= 0:
        return ExecutionDecision(
            "UNKNOWN",
            "invalid_order",
            **base,
            filled_qty=None,
            fill_price=None,
            quote_age_ms=None,
            displayed_qty=None,
        )

    if bid is None or ask is None or ask < bid:
        return ExecutionDecision(
            "UNKNOWN",
            "invalid_top_of_book",
            **base,
            filled_qty=None,
            fill_price=None,
            quote_age_ms=None,
            displayed_qty=None,
        )

    # If the source supplies a realtime flag, False fails closed.
    if "realtime" in quote and quote.get("realtime") is not True:
        return ExecutionDecision(
            "UNKNOWN",
            "quote_not_realtime",
            **base,
            filled_qty=None,
            fill_price=None,
            quote_age_ms=None,
            displayed_qty=None,
        )

    age_ms = _quote_age_ms(quote, now, side="ASK")

    if age_ms is None:
        return ExecutionDecision(
            "UNKNOWN",
            "missing_quote_timestamp",
            **base,
            filled_qty=None,
            fill_price=None,
            quote_age_ms=None,
            displayed_qty=None,
        )

    if age_ms < -1000.0 or age_ms > max_quote_age_ms:
        return ExecutionDecision(
            "UNKNOWN",
            "stale_or_future_quote",
            **base,
            filled_qty=None,
            fill_price=None,
            quote_age_ms=age_ms,
            displayed_qty=None,
        )

    marketable = (
        ask < limit
        if require_trade_through
        else ask <= limit
    )

    if not marketable:
        return ExecutionDecision(
            "ZERO",
            "ask_above_limit",
            **base,
            filled_qty=0,
            fill_price=None,
            quote_age_ms=age_ms,
            displayed_qty=None,
        )

    raw_size = (
        quote.get("ask_size_raw")
        if quote.get("ask_size_raw") is not None
        else quote.get("ask_size")
    )

    size = _number(raw_size)

    if size is None:
        return ExecutionDecision(
            "UNKNOWN",
            "marketable_but_ask_size_missing",
            **base,
            filled_qty=None,
            fill_price=None,
            quote_age_ms=age_ms,
            displayed_qty=None,
        )

    displayed_qty = max(
        0,
        math.floor(size * float(ask_size_multiplier)),
    )

    filled_qty = min(requested_qty, displayed_qty)

    if filled_qty <= 0:
        return ExecutionDecision(
            "ZERO",
            "no_displayed_ask_size",
            **base,
            filled_qty=0,
            fill_price=None,
            quote_age_ms=age_ms,
            displayed_qty=displayed_qty,
        )

    if filled_qty < requested_qty:
        return ExecutionDecision(
            "PARTIAL",
            "displayed_ask_size_below_quantity",
            **base,
            filled_qty=filled_qty,
            fill_price=ask,
            quote_age_ms=age_ms,
            displayed_qty=displayed_qty,
        )

    return ExecutionDecision(
        "FULL",
        "marketable_with_displayed_size",
        **base,
        filled_qty=filled_qty,
        fill_price=ask,
        quote_age_ms=age_ms,
        displayed_qty=displayed_qty,
    )


def executable_long_mark(
    quote: Mapping[str, Any] | None,
    *,
    now: datetime | str | None = None,
    max_quote_age_ms: float = 2000.0,
) -> dict[str, Any]:
    """Return a fresh executable BID liquidation mark for a long."""

    now = _utc(now)
    quote = quote or {}

    bid = _positive(quote.get("bid"))
    ask = _positive(quote.get("ask"))

    def unknown(reason, age=None):
        result = {
            "state": "UNKNOWN",
            "reason": reason,
            "price": None,
            "execution_model": EXECUTION_MODEL,
        }
        if age is not None:
            result["quote_age_ms"] = age
        return result

    if bid is None or ask is None or ask < bid:
        return unknown("invalid_top_of_book")

    if "realtime" in quote and quote.get("realtime") is not True:
        return unknown("quote_not_realtime")

    age_ms = _quote_age_ms(quote, now, side="BID")

    if age_ms is None:
        return unknown("missing_quote_timestamp")

    if age_ms < -1000.0 or age_ms > max_quote_age_ms:
        return unknown("stale_or_future_quote", age_ms)

    return {
        "state": "EXECUTABLE",
        "reason": "fresh_bid",
        "price": bid,
        "bid": bid,
        "ask": ask,
        "quote_age_ms": age_ms,
        "execution_model": EXECUTION_MODEL,
        "price_source": "BID",
    }
