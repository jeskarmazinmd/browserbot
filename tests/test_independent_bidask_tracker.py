import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bidask_paper_outcome_tracker import (
    IndependentBidAskPaperTracker,
)


NOW = datetime(2026, 9, 18, 15, 0, tzinfo=timezone.utc)


def quote(now, bid=9.99, ask=10.01):
    ms = now.timestamp() * 1000
    return {
        "bid": bid, "ask": ask,
        "bid_size_raw": 100, "ask_size_raw": 100,
        "bid_time_ms": ms, "ask_time_ms": ms, "realtime": True,
    }


def signal(setup):
    return {
        "setup_id": setup, "strategy_id": "C3N25S10", "symbol": "XYZ",
        "timestamp": NOW.isoformat(), "entry_price": 10.0,
        "target_price": 10.5, "stop_price": 9.5,
    }


class IndependentBidAskTrackerTests(unittest.TestCase):
    def test_owns_entry_and_exit_without_parent_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = IndependentBidAskPaperTracker(temp)
            self.assertTrue(tracker.register_signal(signal("one"), quote(NOW), NOW))
            self.assertEqual(tracker.active["one"]["entry_price"], 10.01)
            self.assertFalse((Path(temp) / "paper_signal_outcomes.jsonl").exists())
            self.assertFalse((Path(temp) / "paper_signal_v3_bidask_repricing_outcomes.jsonl").exists())

            later = NOW + timedelta(minutes=1)
            exits = tracker.update_quotes({"XYZ": quote(later, bid=10.6, ask=10.62)}, later)
            self.assertEqual(len(exits), 1)
            self.assertEqual(exits[0]["exit_price"], 10.6)
            self.assertEqual(exits[0]["exit_reason"], "TARGET")
            self.assertAlmostEqual(exits[0]["return_pct"], (10.6 / 10.01 - 1) * 100)

            recovered = IndependentBidAskPaperTracker(temp)
            self.assertFalse(recovered.active)
            self.assertFalse(recovered.register_signal(signal("one"), quote(NOW), NOW))

    def test_missing_or_stale_signal_cycle_quote_never_fills_later(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = IndependentBidAskPaperTracker(temp)
            self.assertFalse(tracker.register_signal(signal("missing"), None, NOW))
            stale = quote(NOW - timedelta(minutes=1))
            self.assertFalse(tracker.register_signal(signal("stale"), stale, NOW))
            self.assertFalse(tracker.pending)
            self.assertFalse(tracker.active)
            self.assertEqual(tracker.update_quotes({"XYZ": quote(NOW)}, NOW), [])

            rows = [
                json.loads(line)
                for line in tracker.ledger_path.read_text().splitlines()
            ]
            self.assertEqual([row["event_type"] for row in rows], [
                "PAPER_ENTRY_REJECTED", "PAPER_ENTRY_REJECTED",
            ])
            self.assertEqual({row["setup_id"] for row in rows}, {"missing", "stale"})

    def test_target_below_executable_ask_is_rejected_and_audited(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = IndependentBidAskPaperTracker(temp)
            candidate = signal("below-ask")
            candidate["target_price"] = 10.005
            self.assertFalse(tracker.register_signal(candidate, quote(NOW), NOW))
            self.assertFalse(tracker.active)
            self.assertFalse(tracker.pending)
            rows = [json.loads(line) for line in tracker.ledger_path.read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["event_type"], "PAPER_ENTRY_REJECTED")
            self.assertEqual(rows[0]["execution"]["reason"], "target_not_above_entry_ask")
            self.assertFalse(tracker.register_signal(candidate, quote(NOW), NOW))

    def test_entry_bid_below_stop_is_rejected_before_opening(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = IndependentBidAskPaperTracker(temp)
            candidate = signal("stop-crossed")
            candidate["stop_price"] = 10.0
            self.assertFalse(tracker.register_signal(candidate, quote(NOW), NOW))
            self.assertFalse(tracker.active)
            rows = [json.loads(line) for line in tracker.ledger_path.read_text().splitlines()]
            self.assertEqual(rows[0]["execution"]["reason"], "stop_already_crossed_at_entry_bid")
            self.assertFalse(tracker.pending)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["event_type"], "PAPER_ENTRY_REJECTED")
            self.assertFalse(tracker.register_signal(candidate, quote(NOW), NOW))



if __name__ == "__main__":
    unittest.main()
