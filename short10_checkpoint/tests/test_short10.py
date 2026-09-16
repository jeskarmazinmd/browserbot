import importlib
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    sys.modules["requests"] = types.SimpleNamespace()

from short_paper_tracker import ShortPaperTracker
from short_shadow_worker import fresh, normalize

IDS = ("SHTMOM1", "SHTACC1", "SHTBRK1", "SHTFAIL1", "SHTREL1", "SHTBRD1", "SHTOVER1", "SHTGAP1", "SHTVOL1", "SHTMKT1")


def q(symbol="NVDA", bid=100.0, ask=100.1, close=101.0):
    return {"symbol": symbol, "realtime": True, "bid": bid, "ask": ask, "close": close}


class ShortStrategyTests(unittest.TestCase):
    def test_all_are_independent_paper_only_short_modules(self):
        for sid in IDS:
            module = importlib.import_module(f"short_strategies.strategy_{sid.lower()}")
            self.assertEqual(module.SIDE, "SHORT")
            self.assertTrue(module.PAPER_ONLY)
            self.assertFalse(module.LIVE_ORDER_PLACEMENT)
            text = Path(module.__file__).read_text()
            self.assertNotIn("place_order", text)
            self.assertNotIn("PaperOutcomeTracker", text)
            self.assertNotIn("strategies.strategy_", text)

    def test_downtrend_emits_only_short(self):
        module = importlib.import_module("short_strategies.strategy_shtmom1")
        strategy = module.Strategy()
        start = datetime(2026, 8, 10, 13, 30, tzinfo=timezone.utc)
        emitted = []
        for i in range(35):
            price = 105 - i * .12
            emitted.extend(strategy.evaluate({"timestamp": start + timedelta(minutes=i), "quotes": {"NVDA": q(bid=price, ask=price + .05)}}))
        self.assertTrue(emitted)
        self.assertEqual({x["side"] for x in emitted}, {"SHORT"})

    def test_normalize_and_freshness_use_executable_quotes(self):
        now = datetime(2026, 8, 10, 14, tzinfo=timezone.utc)
        payload = {"realtime": True, "quote": {"bidPrice": 100, "askPrice": 100.1, "closePrice": 101, "quoteTime": int(now.timestamp() * 1000)}, "reference": {"description": "Test"}}
        item = normalize("NVDA", payload)
        self.assertEqual(item["bid"], 100)
        self.assertEqual(item["ask"], 100.1)
        self.assertTrue(fresh(item, now))
        item["quoteTime"] -= 10 * 60 * 1000
        self.assertFalse(fresh(item, now))


class ShortPaperAccountingTests(unittest.TestCase):
    def decision(self, bid=100.0, ask=100.1):
        return {"strategy_id": "TEST", "timestamp": "2026-08-10T14:00:00+00:00", "symbol": "NVDA", "side": "SHORT", "bid": bid, "ask": ask, "target_pct": 1.0, "stop_pct": 1.0, "max_hold_minutes": 60}

    def test_short_sells_at_bid_covers_at_ask_and_uses_whole_shares(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = ShortPaperTracker(root, notional=1000)
            tracker.open_decisions([self.decision()])
            row = next(iter(tracker.active.values()))
            self.assertEqual(row["entry_price"], 100.0)
            self.assertEqual(row["shares"], 10)
            tracker.update("2026-08-10T14:01:00+00:00", {"NVDA": {"bid": 97.9, "ask": 98.0}})
            rows = [__import__("json").loads(x) for x in tracker.ledger.read_text().splitlines()]
            close = rows[-1]
            self.assertEqual(close["exit_reason"], "TARGET")
            self.assertAlmostEqual(close["pnl"], 20.0)
            self.assertAlmostEqual(close["return_pct"], 2.0)

    def test_rising_ask_hits_short_stop_and_loses_money(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = ShortPaperTracker(root, notional=1000)
            tracker.open_decisions([self.decision()])
            tracker.update("2026-08-10T14:01:00+00:00", {"NVDA": {"bid": 101.1, "ask": 101.2}})
            close = __import__("json").loads(tracker.ledger.read_text().splitlines()[-1])
            self.assertEqual(close["exit_reason"], "STOP")
            self.assertLess(close["pnl"], 0)

    def test_long_decision_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = ShortPaperTracker(root)
            d = self.decision(); d["side"] = "LONG"
            tracker.open_decisions([d])
            self.assertEqual(tracker.active, {})

    def test_restart_recovers_open_short(self):
        with tempfile.TemporaryDirectory() as root:
            first = ShortPaperTracker(root); first.open_decisions([self.decision()])
            second = ShortPaperTracker(root)
            self.assertEqual(len(second.active), 1)


if __name__ == "__main__": unittest.main()
