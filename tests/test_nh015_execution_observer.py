import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import nh015_execution_observer as observer
from market_quotes import QuoteSnapshot


class NH015ExecutionObserverTests(unittest.TestCase):
    def quote(self, **changes):
        now_ms = int(self.now.timestamp() * 1000)
        values = dict(
            symbol="TEST", legacy_price=10.0, last=10.0, mark=10.0,
            bid=9.99, ask=10.0, last_size_raw=1, bid_size_raw=200,
            ask_size_raw=200, quote_time_ms=now_ms, trade_time_ms=now_ms,
            bid_time_ms=now_ms, ask_time_ms=now_ms, regular_last=10.0,
            regular_trade_time_ms=now_ms, extended_last=None, last_mic="XNAS",
            bid_mic="XNAS", ask_mic="XNAS", realtime=True,
        )
        values.update(changes)
        return QuoteSnapshot(**values)

    def setUp(self):
        self.now = datetime(2026, 9, 8, 14, 30, tzinfo=timezone.utc)

    def estimate(self, snapshot, limit=10.0, qty=100):
        return observer.estimate_ioc(snapshot, limit, qty, self.now, self.now)

    def test_full_fill_requires_marketable_ask_and_displayed_size(self):
        result = self.estimate(self.quote())
        self.assertEqual(result["outcome"], "FULL")
        self.assertEqual(result["estimated_fill_qty"], 100)
        self.assertEqual(result["estimated_fill_price"], 10.0)

    def test_partial_fill_is_capped_at_displayed_ask_size(self):
        result = self.estimate(self.quote(ask_size_raw=37))
        self.assertEqual(result["outcome"], "PARTIAL")
        self.assertEqual(result["estimated_fill_qty"], 37)

    def test_zero_fill_when_ask_is_above_zero_buffer_limit(self):
        result = self.estimate(self.quote(ask=10.01))
        self.assertEqual(result["outcome"], "ZERO")
        self.assertEqual(result["estimated_fill_qty"], 0)

    def test_missing_size_does_not_invent_quantity(self):
        result = self.estimate(self.quote(ask_size_raw=None))
        self.assertEqual(result["outcome"], "PRICE_MARKETABLE_SIZE_UNKNOWN")
        self.assertNotIn("estimated_fill_qty", result)

    def test_stale_quote_is_unknown(self):
        old = int((self.now - timedelta(seconds=3)).timestamp() * 1000)
        result = self.estimate(self.quote(quote_time_ms=old, ask_time_ms=old))
        self.assertEqual(result["outcome"], "UNKNOWN")
        self.assertEqual(result["reason"], "stale_or_future_quote")

    def test_non_realtime_quote_is_unknown(self):
        result = self.estimate(self.quote(realtime=False))
        self.assertEqual(result["outcome"], "UNKNOWN")
        self.assertEqual(result["reason"], "quote_not_marked_realtime")

    def test_only_exact_live_strategy_signal_is_observed(self):
        self.assertTrue(observer.relevant_signal({"event_type": "SIGNAL", "strategy_id": observer.STRATEGY_ID}))
        self.assertFalse(observer.relevant_signal({"event_type": "SIGNAL", "strategy_id": observer.STRATEGY_ID + "DUP"}))
        self.assertFalse(observer.relevant_signal({"event_type": "REFRAINED", "strategy_id": observer.STRATEGY_ID}))

    def test_module_has_no_trading_client_or_order_method(self):
        source = Path(observer.__file__).read_text()
        self.assertNotIn("SchwabTradeClient", source)
        self.assertNotIn("place_order", source)
        self.assertNotIn("place_ioc", source)
        self.assertNotIn("live_strategy_runner", source)

    def test_supervisor_treats_observer_as_optional(self):
        import supervisor
        self.assertIn("nh015_execution_observer", supervisor.OPTIONAL_WORKERS)
        self.assertFalse(supervisor.worker_exit_is_fatal("nh015_execution_observer"))

    def test_fill_reconciliation_accepts_nested_live_position(self):
        self.assertTrue(observer.reconciliation_event({
            "event_type": "ENTRY_FILL_CONFIRMED",
            "position": {"strategy_id": observer.STRATEGY_ID},
        }))

    def test_reference_quantity_is_explicit_not_actual_quantity(self):
        with patch.object(observer, "REFERENCE_NOTIONAL", 1000.0):
            self.assertEqual(observer.reference_quantity(23.44), 42)


if __name__ == "__main__":
    unittest.main()
