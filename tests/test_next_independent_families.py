import importlib
import unittest
from datetime import datetime, timezone
from pathlib import Path

from engine.events import MarketSnapshot, Quote
from strategies.registry import FLASH_STRATEGY_MODULES, MINUTE_STRATEGIES


FLASH_IDS = {"C1F1MID", "C1F1R65", "C1F1PB15", "J2T15", "J2MID", "J2RB30"}
EMA_IDS = {"EMA1T50", "EMA1V15", "EMA1RR"}


def flash_event(timestamp="2026-08-10T16:30:00+00:00"):
    return {
        "symbol": "XYZ",
        "timestamp": timestamp,
        "signal_window_end": timestamp,
        "flash_drop_pct": 1.2,
        "pre_r2": 0.8,
        "target_price": 10.0,
        "entry_price": 9.5,
        "flash_start_price": 10.4,
    }


class IndependentNextFamiliesTests(unittest.TestCase):
    def test_flash_children_are_direct_and_paper_only(self):
        self.assertTrue(FLASH_IDS <= set(FLASH_STRATEGY_MODULES))
        for strategy_id in FLASH_IDS:
            module = FLASH_STRATEGY_MODULES[strategy_id]
            self.assertTrue(module.PAPER_ONLY)
            self.assertFalse(module.CONFIG["live_order_placement"])
            self.assertEqual(module.FORWARD_START_UTC, "2026-08-10T13:30:00+00:00")

    def test_new_children_do_not_import_parent_modules(self):
        for strategy_id in FLASH_IDS | EMA_IDS:
            source = Path("strategies") / f"strategy_{strategy_id.lower()}.py"
            text = source.read_text().lower()
            for forbidden in ("strategy_c1f1", "strategy_ema1", "strategy_j2", "strategy_b"):
                self.assertNotIn(f"import {forbidden}", text)
                self.assertNotIn(f"from . import {forbidden}", text)

    def test_j2t15_has_independent_entry_filter(self):
        module = FLASH_STRATEGY_MODULES["J2T15"]
        self.assertTrue(module.accepts_flash(flash_event(), 12.0))
        high = flash_event()
        high["target_price"] = 20.0
        self.assertFalse(module.accepts_flash(high, 12.0))

    def test_c1f1_variants_own_r2_and_exit_rules(self):
        event = flash_event()
        self.assertTrue(FLASH_STRATEGY_MODULES["C1F1R65"].accepts_flash(event, 12.0))
        event["pre_r2"] = 0.60
        self.assertFalse(FLASH_STRATEGY_MODULES["C1F1R65"].accepts_flash(event, 12.0))
        refreshed = FLASH_STRATEGY_MODULES["C1F1PB15"].refresh_event_for_entry(flash_event(), 9.6)
        self.assertEqual(refreshed["exit_model"], "c1")
        self.assertEqual(refreshed["pullback_from_high_pct"], 0.15)

    def test_midday_uses_confirmed_entry_time(self):
        module = FLASH_STRATEGY_MODULES["C1F1MID"]
        refreshed = module.refresh_event_for_entry(flash_event(), 9.6)
        refreshed["timestamp"] = "2026-08-10T16:30:00+00:00"  # 12:30 ET
        self.assertTrue(module.validate_confirmed_entry(refreshed, 0.20)[0])
        refreshed["timestamp"] = "2026-08-10T14:30:00+00:00"  # 10:30 ET
        self.assertFalse(module.validate_confirmed_entry(refreshed, 0.20)[0])

    def test_ema_children_are_direct_minute_strategies(self):
        minute_ids = {getattr(x, "name", "") for x in MINUTE_STRATEGIES}
        self.assertTrue(EMA_IDS <= minute_ids)

    def test_ema_children_are_forward_gated(self):
        module = importlib.import_module("strategies.strategy_ema1v15")
        strategy = module.Strategy()
        snap = MarketSnapshot(
            timestamp=datetime(2026, 8, 7, 15, 0, tzinfo=timezone.utc),
            quotes={"XYZ": Quote(price=100.0)},
            expected_symbol_count=1,
            returned_symbol_count=1,
            fetch_duration_seconds=0.1,
            metadata={"confirm_recent_volume_ratio": lambda symbol: 2.0},
        )
        self.assertEqual(strategy.on_snapshot(snap), [])


if __name__ == "__main__":
    unittest.main()
