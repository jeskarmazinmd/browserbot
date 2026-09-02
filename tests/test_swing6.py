import importlib
import json
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import swing_shadow_worker as worker
from swing_paper_tracker import SwingPaperTracker


IDS = ("SWMOM2", "SWMOM5", "SWREV2", "SWBREAK10", "SWTREND20", "SWREL5")


def quote(price):
    return {"bid": price - 0.05, "ask": price + 0.05}


def history(start=100.0, daily=0.01, n=30):
    return [(f"2026-07-{i + 1:02d}", start * ((1 + daily) ** i)) for i in range(n)]


class Swing6Tests(unittest.TestCase):
    def test_six_independent_paper_only_strategies(self):
        loaded = worker.load_strategies()
        self.assertEqual(loaded, [])
        for sid in IDS:
            module = importlib.import_module(f"swing_strategies.strategy_{sid.lower()}")
            self.assertTrue(module.PAPER_ONLY)
            self.assertFalse(module.LIVE_ORDER_PLACEMENT)
            source = Path(module.__file__).read_text()
            self.assertIsNone(re.search(r"(?:from|import)\s+.*strategy_", source))
            self.assertNotIn("place_order", source)

    def test_daily_history_excludes_current_partial_candle(self):
        now = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
        previous = int(datetime(2026, 8, 7, 20, 0, tzinfo=timezone.utc).timestamp() * 1000)
        current = int(datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc).timestamp() * 1000)
        with patch.object(worker, "_get", return_value={"candles": [
            {"datetime": previous, "close": 100},
            {"datetime": current, "close": 999},
        ]}):
            rows = worker.fetch_history("SPY", now)
        self.assertEqual(rows, [("2026-08-07", 100.0)])

    def test_one_history_failure_does_not_destroy_others(self):
        now = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
        def fake(symbol, _now):
            if symbol == "QQQ":
                raise RuntimeError("temporary")
            return [("2026-08-07", 100.0)]
        with tempfile.TemporaryDirectory() as root, \
             patch.object(worker, "DATA_ROOT", Path(root)), \
             patch.object(worker, "HISTORY_PACE_SECONDS", 0), \
             patch.object(worker, "fetch_history", side_effect=fake):
            rows, failures, requests = worker.load_history(now, ("SPY", "QQQ", "IWM"))
        self.assertTrue(rows["SPY"])
        self.assertIn("QQQ", failures)
        self.assertEqual(requests, 3)

    def test_dynamic_universe_is_500_and_not_alphabetic_first_n(self):
        now = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as root, patch.object(worker, "DATA_ROOT", Path(root)):
            path = Path(root, "research_universe_20260810.csv")
            path.write_text("symbol\n" + "\n".join(f"S{i:04d}" for i in range(1200)) + "\n")
            symbols = worker.load_universe(now)
        self.assertEqual(len(symbols), 500)
        self.assertTrue(set(worker.ANCHORS) <= set(symbols))
        self.assertTrue(any(int(x[1:]) > 500 for x in symbols if x.startswith("S") and x[1:].isdigit()))

    def test_daily_history_cache_prevents_repeat_api_warmup(self):
        now = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as root, \
             patch.object(worker, "DATA_ROOT", Path(root)), \
             patch.object(worker, "HISTORY_PACE_SECONDS", 0), \
             patch.object(worker, "fetch_history", return_value=[("2026-08-07", 100.0)]) as fetch:
            first = worker.load_history(now, ("SPY", "QQQ"))
            second = worker.load_history(now, ("SPY", "QQQ"))
        self.assertEqual(first[2], 2)
        self.assertEqual(second[2], 0)
        self.assertEqual(fetch.call_count, 2)

    def test_tracker_holds_across_sessions_then_times_out(self):
        with tempfile.TemporaryDirectory() as root:
            t = SwingPaperTracker(root)
            decision = {"strategy_id": "SWMOM2", "timestamp": "2026-08-10T15:00:00+00:00",
                        "symbol": "SPY", "side": "LONG", "bid": 99.9, "ask": 100.0,
                        "target_pct": 10, "stop_pct": 10, "max_hold_sessions": 2}
            self.assertEqual(t.open_decisions([decision]), 1)
            self.assertEqual(t.update("2026-08-10T19:55:00+00:00", {"SPY": quote(100)}), 0)
            self.assertEqual(len(t.active), 1)
            self.assertEqual(t.update("2026-08-11T19:55:00+00:00", {"SPY": quote(100)}), 1)
            self.assertEqual(len(t.active), 0)

    def test_long_and_short_cross_the_spread(self):
        with tempfile.TemporaryDirectory() as root:
            t = SwingPaperTracker(root, notional=1000)
            base = {"timestamp": "2026-08-10T15:00:00+00:00", "bid": 99.0, "ask": 101.0,
                    "target_pct": 50, "stop_pct": 50, "max_hold_sessions": 1}
            t.open_decisions([{**base, "strategy_id": "L", "symbol": "AAA", "side": "LONG"},
                              {**base, "strategy_id": "S", "symbol": "BBB", "side": "SHORT"}])
            t.update("2026-08-10T19:55:00+00:00", {"AAA": {"bid": 100, "ask": 102},
                                                    "BBB": {"bid": 98, "ask": 100}})
            closes = [json.loads(x) for x in Path(root, "swing_paper_outcomes.jsonl").read_text().splitlines()
                      if json.loads(x)["event"] == "CLOSE"]
            self.assertEqual({x["strategy_id"]: x["exit_price"] for x in closes}, {"L": 100.0, "S": 100.0})

    def test_all_strategies_evaluate_synthetic_completed_history(self):
        now = datetime(2026, 8, 10, 15, 0, tzinfo=timezone.utc)
        hist = {"SPY": history(100, 0.002), "QQQ": history(100, 0.015), "IWM": history(100, -0.015)}
        quotes = {s: quote(float(h[-1][1])) for s, h in hist.items()}
        snap = {"timestamp": now, "completed_daily_history": hist, "quotes": quotes}
        for strategy in worker.load_strategies():
            result = strategy.evaluate(snap)
            self.assertIsInstance(result, list, strategy.name)


if __name__ == "__main__":
    unittest.main()
