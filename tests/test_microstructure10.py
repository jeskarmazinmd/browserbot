import importlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from microstructure_paper_tracker import MicrostructurePaperTracker
from microstructure_shadow_worker import STRATEGIES, fresh, normalize


class Microstructure10Tests(unittest.TestCase):
    def test_exactly_ten_independent_paper_only_strategies(self):
        self.assertEqual(len(STRATEGIES), 10)
        self.assertEqual(len(set(STRATEGIES)), 10)
        for sid in STRATEGIES:
            module = importlib.import_module(f"microstructure_strategies.strategy_{sid.lower()}")
            self.assertTrue(module.PAPER_ONLY, sid)
            self.assertFalse(module.LIVE_ORDER_PLACEMENT, sid)
            source = Path(module.__file__).read_text()
            self.assertNotIn("from microstructure_strategies", source, sid)
            self.assertNotIn("import microstructure_strategies", source, sid)
            self.assertNotIn("place_order", source, sid)

    def test_normalize_preserves_distinct_top_book_fields(self):
        raw = {"realtime": True, "quote": {
            "bidPrice": 100.0, "askPrice": 100.1, "lastPrice": 100.05,
            "mark": 100.04, "bidSize": 80, "askSize": 20,
            "quoteTime": 1786000000000, "bidTime": 1786000000000,
            "askTime": 1786000000001, "tradeTime": 1786000000002,
        }}
        q = normalize("xyz", raw)
        self.assertEqual(q["symbol"], "XYZ")
        self.assertEqual(q["bid"], 100.0)
        self.assertEqual(q["ask"], 100.1)
        self.assertEqual(q["bid_size"], 80)
        self.assertEqual(q["ask_size"], 20)
        self.assertTrue(q["realtime"])

    def test_fresh_rejects_stale_or_nonrealtime_quotes(self):
        now = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        good = {"realtime": True, "bid": 100, "ask": 100.1, "bid_size": 2,
                "ask_size": 3, "quote_time_ms": int(now.timestamp() * 1000)}
        self.assertTrue(fresh(good, now))
        bad = dict(good, realtime=False)
        self.assertFalse(fresh(bad, now))
        stale = dict(good, quote_time_ms=int((now - timedelta(minutes=1)).timestamp() * 1000))
        self.assertFalse(fresh(stale, now))

    def test_tracker_crosses_spread_for_long(self):
        with tempfile.TemporaryDirectory() as root:
            t = MicrostructurePaperTracker(root, notional=1000)
            now = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
            d = {"strategy_id": "X", "timestamp": now, "symbol": "XYZ", "side": "LONG",
                 "bid": 99.9, "ask": 100.0, "target_pct": 10, "stop_pct": 10,
                 "max_hold_minutes": 1}
            self.assertEqual(t.open_decisions([d]), 1)
            self.assertEqual(next(iter(t.active.values()))["entry_price"], 100.0)
            t.update(now + timedelta(minutes=2), {"XYZ": {"bid": 101.0, "ask": 101.1}})
            rows = [__import__("json").loads(x) for x in Path(root, "microstructure_paper_outcomes.jsonl").read_text().splitlines()]
            self.assertAlmostEqual(rows[-1]["pnl"], 10.0)

    def test_tracker_crosses_spread_for_short(self):
        with tempfile.TemporaryDirectory() as root:
            t = MicrostructurePaperTracker(root, notional=1000)
            now = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
            d = {"strategy_id": "X", "timestamp": now, "symbol": "XYZ", "side": "SHORT",
                 "bid": 100.0, "ask": 100.1, "target_pct": 10, "stop_pct": 10,
                 "max_hold_minutes": 1}
            self.assertEqual(t.open_decisions([d]), 1)
            self.assertEqual(next(iter(t.active.values()))["entry_price"], 100.0)
            t.update(now + timedelta(minutes=2), {"XYZ": {"bid": 98.9, "ask": 99.0}})
            rows = [__import__("json").loads(x) for x in Path(root, "microstructure_paper_outcomes.jsonl").read_text().splitlines()]
            self.assertAlmostEqual(rows[-1]["pnl"], 10.0)

    def test_imbalance_strategy_can_generate_prospective_signal(self):
        module = importlib.import_module("microstructure_strategies.strategy_msimb1")
        strategy = module.Strategy()
        start = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        result = []
        for i in range(7):
            bid = 100 + i * .01
            result = strategy.evaluate({"timestamp": start + timedelta(seconds=5*i), "quotes": {
                "XYZ": {"realtime": True, "bid": bid, "ask": bid+.01, "bid_size": 100, "ask_size": 5}
            }})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["side"], "LONG")


if __name__ == "__main__":
    unittest.main()
