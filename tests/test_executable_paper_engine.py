import unittest
from datetime import datetime, timezone

from executable_paper_engine import (
    EXECUTION_MODEL,
    classify_limit_order,
    classify_long_limit,
    executable_long_mark,
    executable_mark,
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


class TestGenericBidAskExecution(unittest.TestCase):

    def _quote(self, **overrides):
        now = datetime.now(timezone.utc)
        ms = int(now.timestamp() * 1000)
        q = {
            "bid": 99.90,
            "ask": 100.00,
            "bid_time_ms": ms,
            "ask_time_ms": ms,
            "realtime": True,
            "bid_size_raw": 50,
            "ask_size_raw": 40,
        }
        q.update(overrides)
        return q, now

    def test_buy_executes_at_ask(self):
        q, now = self._quote()
        r = classify_limit_order(
            q, action="BUY", limit_price=100.00,
            requested_qty=10, now=now,
        )
        self.assertEqual(r.outcome, "FULL")
        self.assertEqual(r.fill_price, 100.00)
        self.assertEqual(r.filled_qty, 10)

    def test_sell_executes_at_bid(self):
        q, now = self._quote()
        r = classify_limit_order(
            q, action="SELL", limit_price=99.90,
            requested_qty=10, now=now,
        )
        self.assertEqual(r.outcome, "FULL")
        self.assertEqual(r.fill_price, 99.90)
        self.assertEqual(r.filled_qty, 10)

    def test_buy_partial_uses_ask_size(self):
        q, now = self._quote(ask_size_raw=4)
        r = classify_limit_order(
            q, action="BUY", limit_price=100.00,
            requested_qty=10, now=now,
        )
        self.assertEqual(r.outcome, "PARTIAL")
        self.assertEqual(r.filled_qty, 4)
        self.assertEqual(r.fill_price, 100.00)

    def test_sell_partial_uses_bid_size(self):
        q, now = self._quote(bid_size_raw=3)
        r = classify_limit_order(
            q, action="SELL", limit_price=99.90,
            requested_qty=10, now=now,
        )
        self.assertEqual(r.outcome, "PARTIAL")
        self.assertEqual(r.filled_qty, 3)
        self.assertEqual(r.fill_price, 99.90)

    def test_stale_sell_is_unknown(self):
        q, now = self._quote()
        q["bid_time_ms"] -= 5000
        r = classify_limit_order(
            q, action="SELL", limit_price=99.90,
            requested_qty=10, now=now,
        )
        self.assertEqual(r.outcome, "UNKNOWN")

    def test_marks_use_liquidation_side(self):
        q, now = self._quote()

        long_mark = executable_mark(q, action="SELL", now=now)
        short_mark = executable_mark(q, action="BUY", now=now)

        self.assertEqual(long_mark["state"], "EXECUTABLE")
        self.assertEqual(long_mark["price"], 99.90)
        self.assertEqual(long_mark["price_source"], "BID")

        self.assertEqual(short_mark["state"], "EXECUTABLE")
        self.assertEqual(short_mark["price"], 100.00)
        self.assertEqual(short_mark["price_source"], "ASK")
