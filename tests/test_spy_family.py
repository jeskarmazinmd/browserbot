from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from engine.events import MarketSnapshot, Quote
from strategies.strategy_spy_br1 import SPYBR1Strategy
from strategies.strategy_spy_ens1 import SPYENS1Strategy
from strategies.strategy_spy_mom1 import SPYMOM1Strategy
from strategies.strategy_spy_mr1 import SPYMR1Strategy
from strategies.strategy_spy_or5 import SPYOR5Strategy
from strategies.strategy_spy_xa1 import SPYXA1Strategy


START = datetime(2026, 8, 5, 13, 30, tzinfo=timezone.utc)
PROXIES = ("QQQ", "IWM", "HYG", "LQD", "UUP")


def snapshot(minute, spy, *, broad_rise=0.0, proxy_rise=0.0):
    quotes = {"SPY": Quote(price=spy)}
    bases = {"QQQ": 100.0, "IWM": 100.0, "HYG": 80.0, "LQD": 100.0, "UUP": 27.0}
    for symbol in PROXIES:
        direction = -1.0 if symbol == "UUP" else 1.0
        quotes[symbol] = Quote(price=bases[symbol] * (1.0 + direction * proxy_rise * minute))
    for index in range(20):
        quotes[f"B{index}"] = Quote(price=50.0 * (1.0 + broad_rise * minute))
    return MarketSnapshot(
        timestamp=START + timedelta(minutes=minute), quotes=quotes,
        expected_symbol_count=len(quotes), returned_symbol_count=len(quotes),
        fetch_duration_seconds=0.0, metadata={"cadence": "minute"},
    )


class SPYFamilyTests(unittest.TestCase):

    def test_five_minute_opening_range_breakout(self):
        strategy = SPYOR5Strategy()
        for minute in range(5):
            self.assertEqual([], strategy.on_snapshot(snapshot(minute, 100.0 + minute * 0.005)))
        signals = strategy.on_snapshot(snapshot(5, 100.10))
        self.assertEqual(1, len(signals))
        self.assertEqual("SPY_OR5", signals[0].strategy_id)
        self.assertEqual("SPY", signals[0].symbol)

    def test_aligned_spy_momentum(self):
        strategy = SPYMOM1Strategy()
        signals = []
        for minute in range(31):
            signals = strategy.on_snapshot(snapshot(minute, 100.0 + minute * 0.03))
        self.assertEqual(1, len(signals))
        self.assertGreaterEqual(signals[0].data["return_5m_pct"], 0.08)
        self.assertGreaterEqual(signals[0].data["return_15m_pct"], 0.15)

    def test_mean_reversion_requires_depth_and_rebound(self):
        strategy = SPYMR1Strategy()
        for minute in range(30):
            strategy.on_snapshot(snapshot(minute, 100.0))
        strategy.on_snapshot(snapshot(30, 99.40))
        strategy.on_snapshot(snapshot(31, 99.35))
        signals = strategy.on_snapshot(snapshot(32, 99.50))
        self.assertEqual(1, len(signals))
        self.assertGreaterEqual(signals[0].data["depth_below_mean_pct"], 0.30)

    def test_breadth_and_cross_asset_confirm_spy(self):
        breadth = SPYBR1Strategy()
        cross = SPYXA1Strategy()
        breadth_signals = []
        cross_signals = []
        for minute in range(21):
            snap = snapshot(minute, 100.0 + minute * 0.03, broad_rise=0.0002, proxy_rise=0.0001)
            breadth_signals = breadth.on_snapshot(snap)
            cross_signals = cross.on_snapshot(snap)
        self.assertEqual(1, len(breadth_signals))
        self.assertEqual(1, len(cross_signals))

    def test_ensemble_emits_with_four_confirmations(self):
        strategy = SPYENS1Strategy()
        signals = []
        for minute in range(31):
            snap = snapshot(minute, 100.0 + minute * 0.03, broad_rise=0.0002, proxy_rise=0.0001)
            signals = strategy.on_snapshot(snap)
        self.assertEqual(1, len(signals))
        self.assertGreaterEqual(signals[0].data["ensemble_score"], 4)


if __name__ == "__main__":
    unittest.main()
