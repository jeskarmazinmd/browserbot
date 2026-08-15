import unittest
from copy import deepcopy

from strategies.m2_forward_family import (
    FAMILY_STRATEGY_IDS,
    derive_m2_family_signals,
)


class M2ForwardFamilyTests(unittest.TestCase):
    def parent(self, timestamp="2026-08-17T13:30:00+00:00"):
        return {
            "strategy_id": "M2",
            "setup_id": "M2|ABCD|2026-08-17T13:30:00+00:00",
            "timestamp": timestamp,
            "symbol": "ABCD",
            "entry_price": 10.0,
            "target_price": 10.1,
            "stop_price": 9.9,
            "exit_model": "target_stop_eod",
            "live_order_placement": False,
        }

    def test_generates_five_unique_children(self):
        rows = derive_m2_family_signals(self.parent())
        self.assertEqual(5, len(rows))
        self.assertEqual(
            set(FAMILY_STRATEGY_IDS),
            {row["strategy_id"] for row in rows},
        )
        self.assertEqual(
            5,
            len({row["setup_id"] for row in rows}),
        )

    def test_fixed_targets(self):
        rows = {
            row["strategy_id"]: row
            for row in derive_m2_family_signals(self.parent())
        }
        self.assertAlmostEqual(10.10, rows["M2F100"]["target_price"])
        self.assertAlmostEqual(10.125, rows["M2T125"]["target_price"])
        self.assertAlmostEqual(10.15, rows["M2T150"]["target_price"])
        for strategy_id in ("M2F100", "M2T125", "M2T150"):
            self.assertEqual(
                "target_stop_eod",
                rows[strategy_id]["exit_model"],
            )

    def test_dynamic_settings(self):
        rows = {
            row["strategy_id"]: row
            for row in derive_m2_family_signals(self.parent())
        }
        self.assertEqual("c2", rows["M2NH15"]["exit_model"])
        self.assertEqual("c2", rows["M2NH30"]["exit_model"])
        self.assertEqual(
            1.0,
            rows["M2NH15"]["activation_gain_pct"],
        )
        self.assertEqual(
            15.0,
            rows["M2NH15"]["no_new_high_seconds"],
        )
        self.assertEqual(
            30.0,
            rows["M2NH30"]["no_new_high_seconds"],
        )

    def test_rejects_pre_forward_signal(self):
        rows = derive_m2_family_signals(
            self.parent("2026-08-17T13:29:59+00:00")
        )
        self.assertEqual([], rows)

    def test_rejects_non_m2(self):
        parent = self.parent()
        parent["strategy_id"] = "EMA1"
        self.assertEqual(
            [],
            derive_m2_family_signals(parent),
        )

    def test_parent_is_not_modified(self):
        parent = self.parent()
        original = deepcopy(parent)
        derive_m2_family_signals(parent)
        self.assertEqual(original, parent)

    def test_every_child_is_paper_only(self):
        for row in derive_m2_family_signals(self.parent()):
            self.assertTrue(row["paper_only"])
            self.assertFalse(row["live_order_placement"])
            self.assertEqual("M2", row["source_strategy_id"])


if __name__ == "__main__":
    unittest.main()
