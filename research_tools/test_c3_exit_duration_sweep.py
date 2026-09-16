from __future__ import annotations

import unittest

try:
    from strategies.c3_exit_duration_sweep import (
        DURATIONS_SECONDS,
        PARENT_STRATEGY_ID,
        SWEEP_STRATEGY_IDS,
        derive_duration_signals,
    )
except ImportError:  # Standalone artifact verification before installation.
    from c3_exit_duration_sweep import (
        DURATIONS_SECONDS,
        PARENT_STRATEGY_ID,
        SWEEP_STRATEGY_IDS,
        derive_duration_signals,
    )


class C3ExitDurationSweepTests(unittest.TestCase):
    def parent(self):
        return {
            "strategy_id": PARENT_STRATEGY_ID,
            "symbol": "KULR",
            "timestamp": "2026-08-17T14:07:25+00:00",
            "setup_id": "C3N25S10|KULR|2026-08-17T14:07:25+00:00",
            "entry_price": 2.5601,
            "target_price": 2.592,
            "stop_price": 2.534499,
            "exit_model": "c2",
            "activation_gain_pct": 0.3,
            "no_new_high_seconds": 30.0,
            "stop_loss_fraction": 0.01,
        }

    def test_exact_ten_non_control_durations(self):
        self.assertEqual((5, 10, 15, 20, 25, 40, 50, 60, 90, 120), DURATIONS_SECONDS)
        self.assertEqual(10, len(SWEEP_STRATEGY_IDS))
        self.assertEqual(10, len(set(SWEEP_STRATEGY_IDS)))
        self.assertNotIn(30, DURATIONS_SECONDS)

    def test_only_duration_and_identity_metadata_change(self):
        parent = self.parent()
        rows = derive_duration_signals(parent)
        self.assertEqual(10, len(rows))
        for row, seconds in zip(rows, DURATIONS_SECONDS):
            self.assertEqual(parent["entry_price"], row["entry_price"])
            self.assertEqual(parent["target_price"], row["target_price"])
            self.assertEqual(parent["stop_price"], row["stop_price"])
            self.assertEqual(parent["activation_gain_pct"], row["activation_gain_pct"])
            self.assertEqual(parent["stop_loss_fraction"], row["stop_loss_fraction"])
            self.assertEqual("c2", row["exit_model"])
            self.assertEqual(float(seconds), row["no_new_high_seconds"])
            self.assertFalse(row["live_order_placement"])
            self.assertEqual(parent["setup_id"], row["source_setup_id"])

    def test_parent_is_not_mutated(self):
        parent = self.parent()
        original = dict(parent)
        derive_duration_signals(parent)
        self.assertEqual(original, parent)

    def test_unrelated_strategy_does_not_fan_out(self):
        parent = self.parent()
        parent["strategy_id"] = "C3N25S15"
        self.assertEqual([], derive_duration_signals(parent))


if __name__ == "__main__":
    unittest.main(verbosity=2)
