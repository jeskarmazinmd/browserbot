import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bidask_multi_leg_paper_tracker import IndependentBidAskMultiLegTracker


NOW = datetime(2026, 9, 18, 15, 0, tzinfo=timezone.utc)


def quote(bid, ask, at=NOW):
    ms = at.timestamp() * 1000
    return {
        "bid": bid, "ask": ask, "bid_size_raw": 100, "ask_size_raw": 100,
        "bid_time_ms": ms, "ask_time_ms": ms, "realtime": True,
    }


def signal(group_id):
    return {
        "group_id": group_id, "strategy_id": "PAIRMR1",
        "timestamp": NOW.isoformat(), "take_profit_pct": 1,
        "stop_loss_pct": 1, "max_hold_minutes": 60,
        "legs": [
            {"symbol": "AAA", "side": "LONG", "entry_price": 10, "weight": 1},
            {"symbol": "BBB", "side": "SHORT", "entry_price": 20, "weight": 1},
        ],
    }


class IndependentMultiLegTests(unittest.TestCase):
    def test_owns_complete_group_without_last_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = IndependentBidAskMultiLegTracker(temp)
            self.assertTrue(tracker.register_signal(
                signal("one"),
                {"AAA": quote(9.99, 10.01), "BBB": quote(19.99, 20.01)},
                NOW,
            ))
            self.assertEqual(tracker.active["one"]["legs"][0]["entry_price"], 10.01)
            self.assertEqual(tracker.active["one"]["legs"][1]["entry_price"], 19.99)
            self.assertFalse((Path(temp) / "multi_leg_paper_outcomes.jsonl").exists())
            later = NOW + timedelta(minutes=61)
            closed = tracker.update_quotes({
                "AAA": quote(10.2, 10.22, later),
                "BBB": quote(19.78, 19.8, later),
            }, later)
            self.assertEqual(len(closed), 1)
            self.assertFalse(tracker.active)

    def test_missing_leg_rejected_in_signal_cycle(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = IndependentBidAskMultiLegTracker(temp)
            self.assertFalse(tracker.register_signal(
                signal("missing"), {"AAA": quote(9.99, 10.01)}, NOW,
            ))
            self.assertFalse(tracker.pending)
            self.assertFalse(tracker.active)
            self.assertEqual(tracker.entry_rejected_groups, 1)
            self.assertEqual(tracker.update_quotes({
                "AAA": quote(9.99, 10.01), "BBB": quote(19.99, 20.01)
            }, NOW), [])


if __name__ == "__main__":
    unittest.main()
