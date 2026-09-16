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

from forex_paper_tracker import ForexPaperTracker, MINI_LOT_UNITS
from forex_shadow_worker import fresh, normalize


IDS = ("FXEUR1", "FXGBP1", "FXJPY1", "FXAUD1", "FXCAD1", "FXCHF1", "FXEGBP1", "FXAN1", "FXUSDB1", "FXLON1")


def quote(symbol="EUR/USD", bid=1.1, ask=1.1002):
    return {"symbol": symbol, "realtime": True, "tradable": True, "bid": bid, "ask": ask}


class ForexStrategyTests(unittest.TestCase):
    def test_all_modules_are_paper_only_and_independent(self):
        for sid in IDS:
            module = importlib.import_module(f"forex_strategies.strategy_{sid.lower()}")
            self.assertTrue(module.PAPER_ONLY)
            self.assertFalse(module.LIVE_ORDER_PLACEMENT)
            self.assertEqual(module.UNITS_PER_LEG, 10_000)
            text = Path(module.__file__).read_text()
            self.assertNotIn("place_order", text)
            self.assertNotIn("strategies.strategy_", text)

    def test_eur_trend_can_emit(self):
        module = importlib.import_module("forex_strategies.strategy_fxeur1")
        strategy = module.Strategy()
        start = datetime(2026, 8, 9, 22, 0, tzinfo=timezone.utc)
        emitted = []
        for i in range(20):
            q = quote(bid=1.1 + i * .0002, ask=1.1001 + i * .0002)
            emitted.extend(strategy.evaluate({"timestamp": start + timedelta(minutes=i), "pairs": {"EUR/USD": q}}))
        self.assertTrue(emitted)
        self.assertEqual(emitted[0]["legs"][0]["side"], "LONG")
        self.assertEqual(emitted[0]["legs"][0]["units"], MINI_LOT_UNITS)

    def test_normalizer_preserves_real_execution_fields(self):
        payload = {
            "realtime": True,
            "quote": {"bidPrice": 1.15573, "askPrice": 1.15586, "bidSize": 2_000_000, "askSize": 1_000_000, "quoteTime": 1786136340826},
            "reference": {"description": "Euro/USDollar Spot", "exchangeName": "GFT", "isTradable": True},
        }
        q = normalize("EUR/USD", payload)
        self.assertEqual(q["bid"], 1.15573)
        self.assertEqual(q["ask"], 1.15586)
        self.assertTrue(q["realtime"])
        self.assertTrue(q["tradable"])

    def test_freshness_gate_rejects_stale_quotes(self):
        now = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        q = quote()
        q["quoteTime"] = int(now.timestamp() * 1000)
        self.assertTrue(fresh(q, now))
        q["quoteTime"] -= 10 * 60 * 1000
        self.assertFalse(fresh(q, now))


class ForexPaperAccountingTests(unittest.TestCase):
    def _decision(self, symbol, side, bid, ask, tp=15):
        return {"strategy_id": "TEST", "timestamp": "2026-08-10T14:00:00+00:00", "legs": [{"symbol": symbol, "side": side, "bid": bid, "ask": ask, "units": 10_000}], "take_profit_dollars": tp, "stop_loss_dollars": 100, "max_hold_minutes": 60}

    def test_usd_quote_pair_crosses_spread_and_reports_dollars(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = ForexPaperTracker(root)
            tracker.open_decisions([self._decision("EUR/USD", "LONG", 1.1000, 1.1002)])
            tracker.update("2026-08-10T14:01:00+00:00", {"EUR/USD": {"bid": 1.1022, "ask": 1.1024}})
            rows = [__import__("json").loads(x) for x in tracker.ledger.read_text().splitlines()]
            self.assertAlmostEqual(rows[-1]["net_pnl_dollars"], 20.0, places=6)
            self.assertEqual(rows[-1]["reason"], "TARGET")

    def test_usd_base_pair_converts_quote_currency_pnl_to_dollars(self):
        leg = {"symbol": "USD/JPY", "side": "LONG", "entry_price": 150.02, "units": 10_000}
        pnl, close, quote_pnl = ForexPaperTracker._leg_pnl_usd(leg, {"bid": 150.32, "ask": 150.34})
        self.assertAlmostEqual(quote_pnl, 3000.0, places=6)
        self.assertAlmostEqual(pnl, 3000.0 / 150.32, places=6)
        self.assertEqual(close, 150.32)

    def test_non_usd_cross_is_fail_closed_for_execution(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = ForexPaperTracker(root)
            tracker.open_decisions([self._decision("EUR/GBP", "LONG", .8565, .8567)])
            self.assertEqual(tracker.active, {})

    def test_restart_recovers_open_group(self):
        with tempfile.TemporaryDirectory() as root:
            first = ForexPaperTracker(root)
            first.open_decisions([self._decision("GBP/USD", "SHORT", 1.35, 1.3502, tp=100)])
            second = ForexPaperTracker(root)
            self.assertEqual(len(second.active), 1)


if __name__ == "__main__":
    unittest.main()
