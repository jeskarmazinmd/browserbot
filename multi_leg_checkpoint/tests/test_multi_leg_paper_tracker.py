import json
import tempfile
import unittest
from datetime import datetime, timezone

from multi_leg_paper_tracker import MultiLegPaperTracker


class MultiLegPaperTrackerTests(unittest.TestCase):
    def _signal(self):
        return {
            "strategy_id": "PAIRTEST",
            "timestamp": "2026-08-10T14:00:00+00:00",
            "group_id": "PAIRTEST|1",
            "legs": [
                {"symbol": "AAA", "side": "LONG", "weight": 1, "entry_price": 100},
                {"symbol": "BBB", "side": "SHORT", "weight": 1, "entry_price": 100},
            ],
            "take_profit_pct": 0.5,
            "stop_loss_pct": 0.5,
            "max_hold_minutes": 60,
        }

    def test_scores_long_and_short_as_one_group(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = MultiLegPaperTracker(root, group_notional=1000)
            self.assertTrue(tracker.register(self._signal()))
            closed = tracker.update(
                {"AAA": 101, "BBB": 99},
                datetime(2026, 8, 10, 14, 1, tzinfo=timezone.utc),
            )
            self.assertEqual(len(closed), 1)
            self.assertAlmostEqual(closed[0]["pnl"], 10.0)
            self.assertAlmostEqual(closed[0]["return_pct"], 1.0)
            self.assertEqual(closed[0]["exit_reason"], "GROUP_TARGET")

    def test_rejects_duplicate_and_malformed_groups(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = MultiLegPaperTracker(root)
            signal = self._signal()
            self.assertTrue(tracker.register(signal))
            self.assertFalse(tracker.register(signal))
            bad = dict(signal, group_id="bad", legs=[signal["legs"][0]])
            self.assertFalse(tracker.register(bad))

    def test_restart_recovers_group_as_one_active_trade(self):
        with tempfile.TemporaryDirectory() as root:
            first = MultiLegPaperTracker(root)
            self.assertTrue(first.register(self._signal()))
            second = MultiLegPaperTracker(root)
            self.assertEqual(set(second.active), {"PAIRTEST|1"})
            status = json.loads(second.status_path.read_text())
            self.assertEqual(status["active_groups"], 1)
            self.assertFalse(status["broker_execution_enabled"])

    def test_stop_is_group_level(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = MultiLegPaperTracker(root, group_notional=1000)
            self.assertTrue(tracker.register(self._signal()))
            closed = tracker.update(
                {"AAA": 99, "BBB": 101},
                datetime(2026, 8, 10, 14, 1, tzinfo=timezone.utc),
            )
            self.assertEqual(closed[0]["exit_reason"], "GROUP_STOP")
            self.assertAlmostEqual(closed[0]["return_pct"], -1.0)


if __name__ == "__main__":
    unittest.main()
