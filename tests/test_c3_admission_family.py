from __future__ import annotations

import unittest

import pandas as pd

from strategies.c3_admission_family import (
    C3AdmissionFamily,
    FAMILY_STRATEGY_IDS,
    FILTERS,
    PARENT_STRATEGY_ID,
)


class C3AdmissionFamilyTests(unittest.TestCase):
    def parent(self, timestamp="2026-08-31T14:10:25+00:00"):
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

    def frame(self):
        rows = []
        minutes = pd.date_range("2026-08-31T13:58:00Z", periods=13, freq="min")
        aaa = [104.0, 103.8, 103.5, 103.2, 102.8, 102.4, 102.0, 101.4, 100.7, 99.9, 99.0, 97.8, 97.0]
        for timestamp, price in zip(minutes, aaa):
            rows.append({"timestamp": timestamp, "symbol": "AAA", "price": price})
            rows.append({"timestamp": timestamp, "symbol": "BBB", "price": 100.0})
        # Entry-minute prices are extreme and must never affect features.
        rows.extend([
            {"timestamp": "2026-08-31T14:10:00Z", "symbol": "AAA", "price": 150.0},
            {"timestamp": "2026-08-31T14:10:00Z", "symbol": "BBB", "price": 50.0},
        ])
        return pd.DataFrame(rows)

    def test_inventory_is_unique_and_omits_slope_aliases(self):
        self.assertEqual(11, len(FAMILY_STRATEGY_IDS))
        self.assertEqual(11, len(set(FAMILY_STRATEGY_IDS)))
        self.assertFalse(any(rule["feature"].startswith("slope_") for rule in FILTERS.values()))

    def test_features_stop_before_entry_minute(self):
        engine = C3AdmissionFamily()
        features = engine.features(self.parent(), self.frame())
        self.assertLess(features["ret_1m"], 0)
        self.assertAlmostEqual(0.0, features["dist_from_3m_low"])
        self.assertEqual(1.0, features["signal_density_5m"])

    def test_children_keep_parent_trade_terms_and_are_paper_only(self):
        parent = self.parent()
        children = C3AdmissionFamily().derive(parent, self.frame())
        self.assertTrue(children)
        for child in children:
            self.assertEqual(parent["entry_price"], child["entry_price"])
            self.assertEqual(parent["target_price"], child["target_price"])
            self.assertEqual(parent["stop_price"], child["stop_price"])
            self.assertEqual(parent["exit_model"], child["exit_model"])
            self.assertEqual(parent["setup_id"], child["source_setup_id"])
            self.assertTrue(child["paper_only"])
            self.assertFalse(child["live_order_placement"])

    def test_missing_features_fail_closed(self):
        children = C3AdmissionFamily().derive(
            self.parent(),
            pd.DataFrame(columns=["timestamp", "symbol", "price"]),
        )
        self.assertEqual([], children)

    def test_pre_start_and_unrelated_do_not_emit(self):
        engine = C3AdmissionFamily()
        self.assertEqual([], engine.derive(self.parent("2026-08-28T14:10:25Z"), self.frame()))
        other = self.parent()
        other["strategy_id"] = "C3N25S15"
        self.assertEqual([], engine.derive(other, self.frame()))

    def test_density_arm_counts_canonical_entries_inclusive(self):
        engine = C3AdmissionFamily()
        parents = [
            self.parent("2026-08-31T14:10:25+00:00")
            for _ in range(14)
        ]
        for index, parent in enumerate(parents):
            parent["symbol"] = f"A{index:02d}"
            parent["setup_id"] = f"{PARENT_STRATEGY_ID}|A{index:02d}|batch"
        emitted = engine.derive_batch(parents, self.frame())
        density_sources = {
            row["source_setup_id"]
            for row in emitted
            if row["strategy_id"] == "C3F_DEN5"
        }
        self.assertEqual({parent["setup_id"] for parent in parents}, density_sources)


if __name__ == "__main__":
    unittest.main()
