import json
import tempfile
import unittest
from datetime import datetime, timezone

from paper_outcome_tracker import PaperOutcomeTracker


def signal(setup_id="S|XYZ|2026-08-03T14:00:00+00:00"):
    return {
        "setup_id": setup_id,
        "strategy_id": "S",
        "symbol": "XYZ",
        "timestamp": "2026-08-03T14:00:00+00:00",
        "entry_price": 100,
        "target_price": 106,
        "stop_price": 95,
    }


class PaperOutcomeTrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.tracker = PaperOutcomeTracker(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_register_deduplicates(self):
        self.assertTrue(self.tracker.register(signal()))
        self.assertFalse(self.tracker.register(signal()))
        self.assertEqual(len(self.tracker.active), 1)

    def test_target_and_stop_close_at_threshold(self):
        self.tracker.register(signal("target"))
        self.tracker.register(signal("stop"))
        target = self.tracker.update(
            {"XYZ": 107}, datetime(2026, 8, 3, 15, tzinfo=timezone.utc)
        )
        self.assertEqual({row["exit_reason"] for row in target}, {"TARGET"})
        self.assertAlmostEqual(target[0]["pnl"], 60)

        other = signal("other-stop")
        other["symbol"] = "ABC"
        self.tracker.register(other)
        stopped = self.tracker.update(
            {"ABC": 94}, datetime(2026, 8, 3, 16, tzinfo=timezone.utc)
        )
        self.assertEqual(stopped[0]["exit_reason"], "STOP")
        self.assertAlmostEqual(stopped[0]["pnl"], -50)

    def test_c1_activates_then_exits_on_trailing_pullback(self):
        c1 = signal("c1-trail")
        c1.update({
            "strategy_id": "C1F1",
            "exit_model": "c1",
            "activation_gain_pct": 0.3,
            "pullback_from_high_pct": 0.2,
            "stop_loss_fraction": 0.02,
        })
        self.assertTrue(self.tracker.register(c1))

        # +0.31% activates the trailing state machine without exiting.
        rows = self.tracker.update(
            {"XYZ": 100.31},
            datetime(2026, 8, 3, 14, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(rows, [])

        # Establish a new post-activation high.
        rows = self.tracker.update(
            {"XYZ": 101.00},
            datetime(2026, 8, 3, 14, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(rows, [])

        # 100.79 is >0.20% below 101.00, so C1 must trail out.
        rows = self.tracker.update(
            {"XYZ": 100.79},
            datetime(2026, 8, 3, 14, 3, tzinfo=timezone.utc),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["exit_reason"], "TRAIL_PULLBACK")

    def test_c2_breakeven_protection_after_activation(self):
        c2 = signal("c2-breakeven")
        c2.update({
            "strategy_id": "C3N25BE",
            "exit_model": "c2",
            "activation_gain_pct": 0.3,
            "no_new_high_seconds": 30.0,
            "stop_loss_fraction": 0.02,
            "stop_price": 98.0,
            "breakeven_after_activation": True,
        })
        self.assertTrue(self.tracker.register(c2))

        rows = self.tracker.update(
            {"XYZ": 100.40},
            datetime(2026, 8, 3, 14, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(rows, [])

        rows = self.tracker.update(
            {"XYZ": 99.90},
            datetime(2026, 8, 3, 14, 1, 10, tzinfo=timezone.utc),
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["exit_reason"], "BREAKEVEN_PROTECT")
        self.assertAlmostEqual(rows[0]["exit_price"], 100.0)
        self.assertAlmostEqual(rows[0]["pnl"], 0.0)
        self.assertAlmostEqual(rows[0]["stop_price"], 98.0)

    def test_eod_marks_to_observed_quote(self):
        self.tracker.register(signal())
        rows = self.tracker.update(
            {"XYZ": 102}, datetime(2026, 8, 3, 19, 55, tzinfo=timezone.utc)
        )
        self.assertEqual(rows[0]["exit_reason"], "EOD")
        self.assertAlmostEqual(rows[0]["pnl"], 20)

    def test_restart_recovers_active_and_completed_dedupe(self):
        self.tracker.register(signal("open"))
        self.tracker.register(signal("closed"))
        self.tracker.update(
            {"XYZ": 106}, datetime(2026, 8, 3, 15, tzinfo=timezone.utc)
        )
        # Both closed because they share the symbol and thresholds.
        restarted = PaperOutcomeTracker(self.temp.name)
        self.assertEqual(len(restarted.active), 0)
        self.assertFalse(restarted.register(signal("closed")))
        self.assertEqual(restarted.completed, 2)

    def test_invalid_signal_is_ignored(self):
        broken = signal()
        broken.pop("stop_price")
        self.assertFalse(self.tracker.register(broken))
        self.assertFalse(self.tracker.ledger_path.exists())

    def test_rejects_entries_at_or_after_cutoff(self):
        late = signal("late")
        late["timestamp"] = "2026-08-03T19:30:00+00:00"
        self.assertFalse(self.tracker.register(late))
        self.assertEqual(self.tracker.rejected_outside_entry_window, 1)
        self.assertEqual(len(self.tracker.active), 0)

    def test_eod_uses_last_observed_quote_when_snapshot_is_missing_symbol(self):
        self.tracker.register(signal("fallback"))
        self.tracker.update(
            {"XYZ": 103}, datetime(2026, 8, 3, 18, tzinfo=timezone.utc)
        )
        rows = self.tracker.update(
            {}, datetime(2026, 8, 3, 19, 55, tzinfo=timezone.utc)
        )
        self.assertEqual(rows[0]["exit_reason"], "EOD")
        self.assertEqual(rows[0]["exit_price"], 103)

    def test_ledger_contains_entry_and_exit(self):
        self.tracker.register(signal())
        self.tracker.update(
            {"XYZ": 106}, datetime(2026, 8, 3, 15, tzinfo=timezone.utc)
        )
        rows = [json.loads(line) for line in self.tracker.ledger_path.read_text().splitlines()]
        self.assertEqual([row["event_type"] for row in rows], ["PAPER_ENTRY", "PAPER_EXIT"])


if __name__ == "__main__":
    unittest.main()
