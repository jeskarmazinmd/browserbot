import importlib
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# The production image already carries requests.  Keep these unit tests
# runnable in tiny development interpreters that do not install it.
try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    sys.modules["requests"] = types.SimpleNamespace()

from futures_paper_tracker import COMMISSION_PER_CONTRACT_SIDE, FuturesPaperTracker
from futures_shadow_worker import normalize, root_for


IDS = ("FUTMES1", "FUTMNQ1", "FUTMGC1", "FUTMCL1", "FUTM6E1", "FUTMESR1", "FUTMGCR1", "FUTMCLR1", "FUTIDXR1", "FUTXAR1")


def quote(root="/MES", symbol="/MESU26", bid=100.0, ask=100.25, multiplier=5.0):
    return {"root": root, "contractSymbol": symbol, "realtime": True, "bid": bid, "ask": ask, "multiplier": multiplier, "expiration": 123}


class FuturesStrategyTests(unittest.TestCase):
    def test_all_modules_are_paper_only_and_independent(self):
        for sid in IDS:
            module = importlib.import_module(f"futures_strategies.strategy_{sid.lower()}")
            self.assertTrue(module.PAPER_ONLY)
            self.assertFalse(module.LIVE_ORDER_PLACEMENT)
            text = Path(module.__file__).read_text()
            self.assertNotIn("place_order", text)
            self.assertNotIn("strategies.strategy_", text)

    def test_contract_roll_resets_local_history(self):
        module = importlib.import_module("futures_strategies.strategy_futmes1")
        strategy = module.Strategy()
        strategy._push("/MES", quote(bid=100, ask=100.25))
        strategy._push("/MES", quote(bid=101, ask=101.25))
        self.assertEqual(len(strategy._h["/MES"]), 2)
        strategy._push("/MES", quote(symbol="/MESZ26", bid=102, ask=102.25))
        self.assertEqual(len(strategy._h["/MES"]), 1)
        self.assertEqual(strategy._active["/MES"], "/MESZ26")

    def test_trend_can_emit_a_prospective_decision(self):
        module = importlib.import_module("futures_strategies.strategy_futmes1")
        strategy = module.Strategy()
        start = datetime(2026, 8, 9, 22, 0, tzinfo=timezone.utc)
        emitted = []
        for i in range(20):
            q = quote(bid=100 + i * .2, ask=100.25 + i * .2)
            emitted.extend(strategy.evaluate({"timestamp": start + timedelta(minutes=i), "roots": {"/MES": q}}))
        self.assertTrue(emitted)
        self.assertEqual(emitted[0]["legs"][0]["side"], "LONG")
        self.assertTrue(emitted[0]["paper_only"])

    def test_normalizer_preserves_execution_and_contract_fields(self):
        payload = {"realtime": True, "quote": {"bidPrice": 7777, "askPrice": 7777.75, "quoteTime": 1786136400068}, "reference": {"futureMultiplier": 5, "futureExpirationDate": 1789704000000, "futureIsActive": True}}
        q = normalize("/MESU26", payload)
        self.assertEqual(q["bid"], 7777)
        self.assertEqual(q["ask"], 7777.75)
        self.assertEqual(q["multiplier"], 5)
        self.assertEqual(root_for("/MESU26"), "/MES")


class FuturesPaperAccountingTests(unittest.TestCase):
    def test_long_crosses_spread_uses_multiplier_and_roundtrip_commission(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = FuturesPaperTracker(root)
            t = datetime(2026, 8, 10, 14, tzinfo=timezone.utc)
            tracker.open_decisions([{"strategy_id": "TEST", "timestamp": t.isoformat(), "legs": [{"root": "/MES", "symbol": "/MESU26", "side": "LONG", "bid": 100, "ask": 100.25, "multiplier": 5}], "take_profit_dollars": 5, "stop_loss_dollars": 100, "max_hold_minutes": 60}])
            self.assertEqual(tracker.required_symbols(), ["/MESU26"])
            tracker.update(t + timedelta(minutes=1), {"/MESU26": {"bid": 102.25, "ask": 102.5}})
            self.assertEqual(tracker.completed, 1)
            rows = [__import__("json").loads(x) for x in tracker.ledger.read_text().splitlines()]
            close = rows[-1]
            # (102.25 - 100.25) * $5 = $10 gross, then $4.50 commission.
            self.assertAlmostEqual(close["net_pnl_dollars"], 10 - 2 * COMMISSION_PER_CONTRACT_SIDE)
            self.assertEqual(close["reason"], "TARGET")

    def test_restart_keeps_exact_old_contract_required(self):
        with tempfile.TemporaryDirectory() as root:
            t = datetime(2026, 8, 10, 14, tzinfo=timezone.utc)
            first = FuturesPaperTracker(root)
            first.open_decisions([{"strategy_id": "TEST", "timestamp": t.isoformat(), "legs": [{"root": "/MES", "symbol": "/MESU26", "side": "SHORT", "bid": 100, "ask": 100.25, "multiplier": 5}], "take_profit_dollars": 100, "stop_loss_dollars": 100, "max_hold_minutes": 60}])
            second = FuturesPaperTracker(root)
            self.assertEqual(second.required_symbols(), ["/MESU26"])


if __name__ == "__main__":
    unittest.main()
