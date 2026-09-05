from __future__ import annotations

from datetime import datetime, timezone
import unittest

from strategies.c3_nh015_time_of_day import (
    DISCOVERY_PERIOD,
    PARENT_STRATEGY_ID,
    PROSPECTIVE_START_UTC,
    TIME_OF_DAY_STRATEGY_IDS,
    derive_time_of_day_signals,
    evaluate_time_of_day_children,
)


class NH015TimeOfDayTests(unittest.TestCase):
    def parent(self, hour, minute, day=8):
        timestamp = datetime(
            2026, 9, day, hour + 4, minute, tzinfo=timezone.utc
        ).isoformat()
        return {
            "strategy_id": PARENT_STRATEGY_ID,
            "symbol": "TEST",
            "timestamp": timestamp,
            "setup_id": f"{PARENT_STRATEGY_ID}|TEST|{timestamp}",
            "entry_price": 10.0,
            "target_price": 10.2,
            "stop_price": 9.9,
            "exit_model": "c2",
            "no_new_high_seconds": 15.0,
            "live_order_placement": False,
        }

    def ids(self, hour, minute, day=8):
        return {
            row["strategy_id"]
            for row in derive_time_of_day_signals(
                self.parent(hour, minute, day)
            )
        }

    def test_exact_selected_children(self):
        self.assertEqual(
            (
                "C3N25S10NH015T1230",
                "C3N25S10NH015T1500",
                "C3N25S10NH015LATE",
                "C3N25S10NH015XWEAK",
            ),
            TIME_OF_DAY_STRATEGY_IDS,
        )

    def test_selected_admission_rules(self):
        self.assertEqual(
            {"C3N25S10NH015T1230", "C3N25S10NH015XWEAK"},
            self.ids(12, 30),
        )
        self.assertEqual(set(), self.ids(12, 0))
        self.assertEqual(
            {"C3N25S10NH015LATE"},
            self.ids(14, 30),
        )
        self.assertEqual(
            {
                "C3N25S10NH015T1500",
                "C3N25S10NH015LATE",
                "C3N25S10NH015XWEAK",
            },
            self.ids(15, 0),
        )

    def test_discovery_period_is_not_backfilled(self):
        decisions = evaluate_time_of_day_children(self.parent(15, 0, day=4))
        self.assertEqual(4, len(decisions))
        self.assertFalse(any(row["admitted"] for row in decisions))
        self.assertEqual(
            {"before_prospective_start"},
            {row["reason"] for row in decisions},
        )

    def test_children_preserve_mechanics_and_are_paper_only(self):
        parent = self.parent(15, 0)
        for row in derive_time_of_day_signals(parent):
            for key in (
                "entry_price", "target_price", "stop_price", "exit_model",
                "no_new_high_seconds",
            ):
                self.assertEqual(parent[key], row[key])
            self.assertFalse(row["live_order_placement"])
            self.assertTrue(row["experimental_child"])
            self.assertEqual(DISCOVERY_PERIOD, row["discovery_period"])
            self.assertEqual(
                PROSPECTIVE_START_UTC,
                row["prospective_start_utc"],
            )
            self.assertEqual(parent["setup_id"], row["source_setup_id"])

    def test_every_parent_produces_four_observable_decisions(self):
        decisions = evaluate_time_of_day_children(self.parent(10, 0))
        self.assertEqual(4, len(decisions))
        self.assertEqual(set(TIME_OF_DAY_STRATEGY_IDS), {
            row["strategy_id"] for row in decisions
        })
        self.assertEqual(1, sum(row["admitted"] for row in decisions))

    def test_unrelated_parent_is_rejected(self):
        parent = self.parent(10, 0)
        parent["strategy_id"] = "C3N25S10NH015"
        self.assertEqual([], evaluate_time_of_day_children(parent))


if __name__ == "__main__":
    unittest.main(verbosity=2)
