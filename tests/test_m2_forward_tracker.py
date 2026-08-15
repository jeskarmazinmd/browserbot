import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from paper_outcome_tracker import PaperOutcomeTracker
from strategies.m2_forward_family import derive_m2_family_signals


class M2ForwardTrackerTests(unittest.TestCase):
    def parent(self):
        return {
            "strategy_id": "M2",
            "setup_id": "M2|TEST|2026-08-17T14:00:00+00:00",
            "timestamp": "2026-08-17T14:00:00+00:00",
            "symbol": "TEST",
            "entry_price": 10.0,
            "target_price": 10.1,
            "stop_price": 9.9,
            "exit_model": "target_stop_eod",
            "live_order_placement": False,
        }

    def signal(self, strategy_id):
        rows = derive_m2_family_signals(self.parent())
        return next(
            row for row in rows
            if row["strategy_id"] == strategy_id
        )

    def test_fixed_target_closes_at_target(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = PaperOutcomeTracker(root)
            signal = self.signal("M2T125")
            self.assertTrue(tracker.register(signal))

            now = datetime(
                2026, 8, 17, 14, 0, 5,
                tzinfo=timezone.utc,
            )
            closed = tracker.update(
                {"TEST": 10.20},
                now,
            )

            self.assertEqual(1, len(closed))
            self.assertEqual("TARGET", closed[0]["exit_reason"])
            self.assertAlmostEqual(
                10.125,
                closed[0]["exit_price"],
            )

    def test_dynamic_bypasses_target_and_waits_15_seconds(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = PaperOutcomeTracker(root)
            signal = self.signal("M2NH15")
            self.assertTrue(tracker.register(signal))

            activation = datetime(
                2026, 8, 17, 14, 0, 5,
                tzinfo=timezone.utc,
            )

            # This reaches the ordinary +1% target, but c2 must
            # activate instead of recording a fixed-target exit.
            closed = tracker.update(
                {"TEST": 10.10},
                activation,
            )
            self.assertEqual([], closed)

            closed = tracker.update(
                {"TEST": 10.09},
                activation + timedelta(seconds=14),
            )
            self.assertEqual([], closed)

            closed = tracker.update(
                {"TEST": 10.08},
                activation + timedelta(seconds=16),
            )
            self.assertEqual(1, len(closed))
            self.assertEqual(
                "NO_NEW_HIGH",
                closed[0]["exit_reason"],
            )
            self.assertAlmostEqual(
                10.08,
                closed[0]["exit_price"],
            )


if __name__ == "__main__":
    unittest.main()
