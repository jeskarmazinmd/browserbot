from __future__ import annotations

import unittest

import pandas as pd

from strategies.c3_market_gate_family import (
    C3MarketGateFamily,
    FAMILY_STRATEGY_IDS,
    FORWARD_START_UTC,
    PARENT_STRATEGY_ID,
)


class C3MarketGateFamilyTests(unittest.TestCase):
    def parent(self, timestamp="2026-09-02T14:10:25Z"):
        return {
            "strategy_id": PARENT_STRATEGY_ID,
            "symbol": "AAA",
            "timestamp": timestamp,
            "setup_id": f"{PARENT_STRATEGY_ID}|AAA|{timestamp}",
            "entry_price": 98.0,
            "target_price": 101.0,
            "stop_price": 97.02,
            "exit_model": "c2",
        }

    def frame(self, weak=False):
        rows = []
        minutes = pd.date_range("2026-09-02T14:00:00Z", periods=11, freq="min")
        for index in range(60):
            symbol = f"U{index:02d}"
            for offset, timestamp in enumerate(minutes):
                direction = -1 if weak or index < 10 else 1
                step = 0.20 if weak else 0.05
                rows.append({
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "price": 100.0 + direction * offset * step,
                })
        for symbol, direction in (("SPY", -1 if weak else 1), ("QQQ", -1 if weak else 1), ("IWM", -1 if weak else 1)):
            for offset, timestamp in enumerate(minutes):
                rows.append({
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "price": 100.0 + direction * offset * (0.20 if weak else 0.10),
                })
        # Entry-minute shock must not affect the frozen 14:09 cutoff.
        rows.append({"timestamp": "2026-09-02T14:10:00Z", "symbol": "IWM", "price": 50.0})
        return pd.DataFrame(rows)

    def test_inventory_is_small_and_unique(self):
        self.assertEqual(6, len(FAMILY_STRATEGY_IDS))
        self.assertEqual(6, len(set(FAMILY_STRATEGY_IDS)))

    def test_features_stop_before_entry_minute(self):
        features = C3MarketGateFamily().features(self.parent()["timestamp"], self.frame())
        self.assertGreater(features["iwm_ret_5m"], 0)
        self.assertGreater(features["green_pct_5m"], 35)

    def test_favorable_market_emits_unchanged_paper_children(self):
        parent = self.parent()
        engine = C3MarketGateFamily()
        children = engine.derive_batch([parent], self.frame())
        self.assertEqual(set(FAMILY_STRATEGY_IDS), {row["strategy_id"] for row in children})
        for child in children:
            self.assertEqual(parent["entry_price"], child["entry_price"])
            self.assertEqual(parent["target_price"], child["target_price"])
            self.assertEqual(parent["stop_price"], child["stop_price"])
            self.assertTrue(child["paper_only"])
            self.assertFalse(child["live_order_placement"])

    def test_weak_market_records_refrains(self):
        engine = C3MarketGateFamily()
        children = engine.derive_batch([self.parent()], self.frame(weak=True))
        self.assertEqual([], children)
        self.assertEqual(6, len(engine.last_decisions))
        self.assertTrue(all(not decision["passed"] for decision in engine.last_decisions))

    def test_missing_breadth_fails_closed_without_blocking_index_arms(self):
        frame = self.frame().query("symbol in ['SPY', 'QQQ', 'IWM']")
        engine = C3MarketGateFamily()
        children = engine.derive_batch([self.parent()], frame)
        child_ids = {row["strategy_id"] for row in children}
        self.assertIn("C3MG_IWM5", child_ids)
        self.assertIn("C3MG_SPY5", child_ids)
        self.assertNotIn("C3MG_BRD35", child_ids)
        breadth_decision = next(row for row in engine.last_decisions if row["strategy_id"] == "C3MG_BRD35")
        self.assertEqual("missing_feature", breadth_decision["reason"])

    def test_pre_start_and_unrelated_do_not_emit(self):
        engine = C3MarketGateFamily()
        self.assertEqual([], engine.derive_batch([self.parent("2026-09-01T14:10:25Z")], self.frame()))
        other = self.parent(FORWARD_START_UTC)
        other["strategy_id"] = "C3N25S15"
        self.assertEqual([], engine.derive_batch([other], self.frame()))


if __name__ == "__main__":
    unittest.main()
