import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bidask_paper_outcome_tracker import (
    CycleQuoteProvider, IndependentBidAskPaperTracker,
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
    def test_new_signal_quote_requests_are_bounded_per_cycle(self):
        calls = []
        cache = CycleQuoteProvider(
            lambda symbols: calls.append(list(symbols)) or {},
            max_targeted_symbols=2,
        )
        cache.reset()
        cache(["AAA"])
        cache(["BBB"])
        cache(["CCC"])
        cache(["CCC"])
        self.assertEqual(calls, [["AAA"], ["BBB"]])
        cache.reset()
        cache(["CCC"])
        self.assertEqual(calls[-1], ["CCC"])

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


if __name__ == "__main__":
    unittest.main()
