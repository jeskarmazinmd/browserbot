import inspect
import unittest
from datetime import datetime, timezone

from engine.events import MarketSnapshot, Quote
from strategies import strategy_gtmx, strategy_ptd1x, strategy_qtd1x
from strategies.registry import MINUTE_STRATEGIES


MODULES = (strategy_qtd1x, strategy_ptd1x, strategy_gtmx)


class OrthogonalComboTests(unittest.TestCase):
    def test_modules_are_paper_only_and_forward_gated(self):
        for module in MODULES:
            self.assertTrue(module.PAPER_ONLY)
            self.assertFalse(module.LIVE_ORDER_PLACEMENT)
            self.assertEqual(module.FORWARD_START_UTC, "2026-08-10T13:30:00+00:00")

    def test_modules_are_direct_minute_strategies(self):
        active = {strategy.name: strategy for strategy in MINUTE_STRATEGIES}
        self.assertTrue({"QTD1X", "PTD1X", "GTMX"} <= set(active))
        for strategy_id in ("QTD1X", "PTD1X", "GTMX"):
            self.assertFalse(getattr(active[strategy_id], "LIVE_ORDER_PLACEMENT", False))

    def test_no_parent_strategy_or_shared_indicator_imports(self):
        forbidden = (
            "strategy_q", "strategy_p", "strategy_td1", "strategy_gt1",
            "strategy_m", "derived_runtime", "snapshot_common", "detectors.",
        )
        for module in MODULES:
            source = inspect.getsource(module)
            for text in forbidden:
                self.assertNotIn(text, source, (module.STRATEGY_ID, text))

    def test_qtd1_q_mode_owns_target_and_stop_math(self):
        start = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        history = []
        for i in range(34):
            price = 100.0 + (0.01 if i % 2 else 0.0)
            history.append((start.replace(minute=0) + __import__("datetime").timedelta(minutes=i), price, 1000 + i * 10))
        history[-4] = (history[-4][0], 100.0, history[-4][2])
        history[-3] = (history[-3][0], 98.5, history[-3][2])
        history[-2] = (history[-2][0], 98.55, history[-2][2])
        history[-1] = (history[-1][0], 98.70, history[-1][2])
        result = strategy_qtd1x._q_candidate(history, history[-1][0])
        self.assertIsNotNone(result)
        self.assertGreater(result["target_price"], result["entry_price"])
        self.assertAlmostEqual(result["stop_price"], result["entry_price"] * 0.95)

    def test_ptd1_p_mode_requires_pretrend_and_reversal(self):
        from datetime import timedelta
        start = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        history = []
        for i in range(34):
            price = 100.0 + 0.04 * min(i, 30)
            history.append((start + timedelta(minutes=i), price, 1000 + i * 10))
        history[-4] = (history[-4][0], 101.2, history[-4][2])
        history[-3] = (history[-3][0], 99.7, history[-3][2])
        history[-2] = (history[-2][0], 99.75, history[-2][2])
        history[-1] = (history[-1][0], 99.9, history[-1][2])
        result = strategy_ptd1x._p_candidate(history, history[-1][0])
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result["pre_return_pct"], 0.75)
        self.assertGreaterEqual(result["pre_r2"], 0.50)

    def test_gtmx_gt_mode_detects_independent_trend(self):
        from datetime import timedelta
        start = datetime(2026, 8, 10, 14, 0, tzinfo=timezone.utc)
        history = [
            (start + timedelta(minutes=i), 100.0 + i * 0.03, 1000 + i * 10)
            for i in range(31)
        ]
        result = strategy_gtmx._gt_candidate(history, history[-1][0])
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result["trend_return_30m_pct"], 0.60)
        self.assertGreaterEqual(result["trend_r2"], 0.35)


if __name__ == "__main__":
    unittest.main()
