from datetime import datetime, timezone

from executable_paper_engine import (
    EXECUTION_MODEL,
    classify_long_limit,
    executable_long_mark,
)


NOW = datetime(2026, 9, 8, 18, 0, tzinfo=timezone.utc)
NOW_MS = int(NOW.timestamp() * 1000)


def quote(**overrides):
    result = {
        "bid": 9.99,
        "ask": 10.00,
        "bid_time_ms": NOW_MS,
        "ask_time_ms": NOW_MS,
        "realtime": True,
        "ask_size_raw": 500,
    }
    result.update(overrides)
    return result


def test_full_fill_uses_ask():
    result = classify_long_limit(
        quote(),
        limit_price=10.00,
        requested_qty=100,
        now=NOW,
    )

    assert result.outcome == "FULL"
    assert result.filled_qty == 100
    assert result.fill_price == 10.00


def test_partial_fill_is_limited_by_displayed_size():
    result = classify_long_limit(
        quote(ask_size_raw=40),
        limit_price=10.00,
        requested_qty=100,
        now=NOW,
    )

    assert result.outcome == "PARTIAL"
    assert result.filled_qty == 40
    assert result.fill_price == 10.00


def test_ask_above_limit_does_not_fill():
    result = classify_long_limit(
        quote(ask=10.02),
        limit_price=10.00,
        requested_qty=100,
        now=NOW,
    )

    assert result.outcome == "ZERO"
    assert result.filled_qty == 0
    assert result.fill_price is None


def test_stale_quote_is_unknown_not_rejection():
    result = classify_long_limit(
        quote(ask_time_ms=NOW_MS - 10_000),
        limit_price=10.00,
        requested_qty=100,
        now=NOW,
    )

    assert result.outcome == "UNKNOWN"
    assert result.reason == "stale_or_future_quote"


def test_missing_size_is_unknown():
    result = classify_long_limit(
        quote(ask_size_raw=None),
        limit_price=10.00,
        requested_qty=100,
        now=NOW,
    )

    assert result.outcome == "UNKNOWN"
    assert result.reason == "marketable_but_ask_size_missing"


def test_trade_through_requires_ask_below_limit():
    result = classify_long_limit(
        quote(ask=10.00),
        limit_price=10.00,
        requested_qty=100,
        now=NOW,
        require_trade_through=True,
    )

    assert result.outcome == "ZERO"


def test_long_mark_uses_bid():
    result = executable_long_mark(
        quote(bid=10.07, ask=10.08),
        now=NOW,
    )

    assert result["state"] == "EXECUTABLE"
    assert result["price"] == 10.07
    assert result["price_source"] == "BID"
    assert result["execution_model"] == EXECUTION_MODEL


def test_stale_bid_cannot_mark_open_position():
    result = executable_long_mark(
        quote(bid_time_ms=NOW_MS - 10_000),
        now=NOW,
    )

    assert result["state"] == "UNKNOWN"
    assert result["price"] is None


def test_crossed_quote_is_unknown():
    result = classify_long_limit(
        quote(bid=10.01, ask=10.00),
        limit_price=10.00,
        requested_qty=100,
        now=NOW,
    )

    assert result.outcome == "UNKNOWN"
