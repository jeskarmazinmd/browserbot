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

    @staticmethod
    def stability_sample(delay, bid, ask, size=500):
        return {
            "target_sample_delay_ms": delay, "outcome": "FULL",
            "bid": bid, "ask": ask, "ask_size_raw": size,
        }

    def test_stability_family_uses_subsecond_quote_evidence(self):
        rows = [
            self.stability_sample(0, 99.96, 100.00),
            self.stability_sample(100, 99.97, 100.00),
            self.stability_sample(250, 99.98, 100.00),
            self.stability_sample(1000, 99.98, 100.00),
        ]
        decisions = observer.evaluate_stability_policies(rows, 100.0, 101.0, 5)
        by_id = {row["strategy_id"]: row for row in decisions}
        self.assertEqual(set(observer.STABILITY_POLICY_IDS), set(by_id))
        for strategy_id in (
            "C3N25S10NH015XBIDSTABLE250", "C3N25S10NH015XBIDUP250",
            "C3N25S10NH015XSTABLE1000", "C3N25S10NH015XASKPERSIST",
            "C3N25S10NH015XSIZE2X", "C3N25S10NH015XEDGE3STABLE",
        ):
            self.assertTrue(by_id[strategy_id]["admitted"])
        self.assertFalse(by_id["C3N25S10NH015XDEPTHIMB"]["admitted"])
        self.assertEqual("LEVEL2_NOT_CONNECTED", by_id["C3N25S10NH015XDEPTHIMB"]["reason"])

    def test_falling_bid_rejects_stability_gates(self):
        rows = [
            self.stability_sample(0, 99.96, 100.00),
            self.stability_sample(100, 99.94, 99.98),
            self.stability_sample(250, 99.90, 99.95),
            self.stability_sample(1000, 99.88, 99.92),
        ]
        decisions = observer.evaluate_stability_policies(rows, 100.0, 101.0, 5)
        by_id = {row["strategy_id"]: row for row in decisions}
        self.assertFalse(by_id["C3N25S10NH015XBIDSTABLE250"]["admitted"])
        self.assertFalse(by_id["C3N25S10NH015XBIDUP250"]["admitted"])
        self.assertFalse(by_id["C3N25S10NH015XEDGE3STABLE"]["admitted"])

    @staticmethod
    def last_sample(delay, ask, outcome="FULL", fill_qty=10):
        return {
            "target_sample_delay_ms": delay,
            "outcome": outcome,
            "reason": "test",
            "bid": ask - 0.01,
            "ask": ask,
            "estimated_fill_qty": fill_qty,
        }

    def test_last_price_family_separates_ioc_250_and_1000ms_fills(self):
        rows = [
            self.last_sample(0, 100.02, "ZERO", 0),
            self.last_sample(100, 100.01, "ZERO", 0),
            self.last_sample(250, 100.00),
            self.last_sample(500, 99.99),
            self.last_sample(1000, 99.98),
        ]
        decisions = observer.evaluate_last_price_policies(rows, 100.0, 10)
        by_id = {row["strategy_id"]: row for row in decisions}
        self.assertEqual(set(observer.LAST_PRICE_POLICY_IDS), set(by_id))
        self.assertFalse(by_id["C3N25S10NH015XLASTIOC"]["admitted"])
        self.assertTrue(by_id["C3N25S10NH015XLAST250"]["admitted"])
        self.assertEqual(250, by_id["C3N25S10NH015XLAST250"]["fill_delay_ms"])
        self.assertTrue(by_id["C3N25S10NH015XLAST1000"]["admitted"])
        self.assertEqual(250, by_id["C3N25S10NH015XLAST1000"]["fill_delay_ms"])

    def test_last_price_family_requires_complete_displayed_fill(self):
        rows = [
            self.last_sample(0, 100.00, "PARTIAL", 4),
            self.last_sample(100, 100.00, "PARTIAL", 4),
            self.last_sample(250, 100.00, "PARTIAL", 4),
            self.last_sample(500, 100.00, "PARTIAL", 4),
            self.last_sample(1000, 100.00, "PARTIAL", 4),
        ]
        decisions = observer.evaluate_last_price_policies(rows, 100.0, 10)
        self.assertTrue(all(not row["admitted"] for row in decisions))

    def test_last_price_family_never_invents_price_improvement(self):
        rows = [self.last_sample(0, 99.95)]
        decision = observer.evaluate_last_price_policies(rows, 100.0, 10)[0]
        self.assertTrue(decision["admitted"])
        self.assertEqual(99.95, decision["observed_ask"])
        self.assertEqual(100.0, decision["simulated_entry_price"])

    def test_observe_signal_preserves_detection_and_queue_timing(self):
        event = {
            "timestamp": self.now.isoformat(),
            "symbol": "TEST",
            "signal": {
                "setup_id": "C3N25S10NH015|TEST|timing",
                "symbol": "TEST",
                "entry_price": 10.0,
                "target_price": 10.1,
            },
        }
        detected_at = self.now + timedelta(milliseconds=25)
        with (
            patch.object(observer, "SAMPLE_DELAYS_MS", (0,)),
            patch.object(observer, "utc_now", side_effect=[
                detected_at + timedelta(milliseconds=5),
                detected_at + timedelta(milliseconds=5),
                detected_at + timedelta(milliseconds=5),
                detected_at + timedelta(milliseconds=15),
                detected_at + timedelta(milliseconds=20),
            ]),
            patch.object(observer, "fetch_snapshot", return_value=self.quote()),
            patch.object(observer, "_append"),
        ):
            payload = observer.observe_signal(event, detected_at)
        self.assertEqual(detected_at.isoformat(), payload["observer_detected_at"])
        self.assertEqual(5.0, payload["observer_queue_delay_ms"])
        sample = payload["observations"][0]
        self.assertEqual(15.0, sample["sample_delay_from_detection_ms"])
        self.assertEqual(40.0, sample["sample_delay_from_signal_ms"])

    def test_observer_uses_bounded_concurrent_executor(self):
        source = Path(observer.__file__).read_text()
        self.assertIn("ThreadPoolExecutor", source)
        self.assertIn("MAX_CONCURRENT_OBSERVATIONS", source)
        self.assertIn("MAX_INFLIGHT_OBSERVATIONS", source)
        self.assertIn("SIGNAL_OBSERVATION_DROPPED", source)


if __name__ == "__main__":
    unittest.main()
