import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone

# The small review archive may omit dependencies used only by untouched legacy
# code. Use real project modules when available and local stubs only otherwise.
try:
    import executable_paper_engine  # noqa: F401
except ModuleNotFoundError:
    engine = types.ModuleType("executable_paper_engine")
    engine.EXECUTION_MODEL = "BIDASK_EXEC_V1"
    engine.classify_limit_order = lambda *args, **kwargs: None
    engine.executable_mark = lambda *args, **kwargs: None
    sys.modules["executable_paper_engine"] = engine

try:
    import strategies  # noqa: F401
except ModuleNotFoundError:
    strategies = types.ModuleType("strategies")
    strategies.strategy_o = types.SimpleNamespace()
    sys.modules["strategies"] = strategies

from bidask_paper_outcome_tracker import (
    BidAskRepricingTracker,
    IocL1PaperOutcomeTracker,
    BidAskPaperOutcomeTracker,
)
from paper_outcome_tracker import PaperOutcomeTracker


NOW = datetime(2026, 9, 11, 14, 31, tzinfo=timezone.utc)


def signal():
    return {
        "setup_id": "C3N25S10|ABC|2026-09-11T14:31:00+00:00",
        "strategy_id": "C3N25S10",
        "symbol": "ABC",
        "timestamp": NOW.isoformat(),
        "entry_price": 100.0,
        "target_price": 101.0,
        "stop_price": 99.0,
        "exit_model": "c3",
        "paper_notional": 1000.0,
    }


class BidAskRepricingTrackerTest(unittest.TestCase):
    def test_only_accepted_parent_trade_is_registered_and_exit_is_copied(self):
        with tempfile.TemporaryDirectory() as root:
            parent = PaperOutcomeTracker(root)
            self.assertTrue(parent.register(signal()))
            parent_entry = parent.active[signal()["setup_id"]]

            ba = BidAskRepricingTracker(root)
            self.assertTrue(ba.register_parent_entry(parent_entry, now=NOW))
            self.assertEqual(set(ba.pending_entries), {signal()["setup_id"]})

            ba.update_quotes({"ABC": {"bid": 99.9, "ask": 100.1}}, NOW)
            entry = ba.active[signal()["setup_id"]]
            self.assertEqual(entry["entry_price"], 100.1)
            self.assertEqual(entry["entry_timestamp"], parent_entry["entry_timestamp"])
            self.assertEqual(entry["notional"], parent_entry["notional"])
            self.assertEqual(entry["trade_intent"]["trade_id"], signal()["setup_id"])
            self.assertEqual(
                entry["trade_intent"]["source_strategy_id"], "C3N25S10"
            )

            parent_exit = {
                **parent_entry,
                "exit_timestamp": "2026-09-11T14:37:12+00:00",
                "exit_reason": "ADAPTIVE_TRAIL",
                "exit_price": 100.8,
            }
            exits = ba.register_parent_exits(
                [parent_exit], {"ABC": {"bid": 100.7, "ask": 100.8}}, NOW
            )
            self.assertEqual(len(exits), 1)
            self.assertEqual(exits[0]["exit_timestamp"], parent_exit["exit_timestamp"])
            self.assertEqual(exits[0]["exit_reason"], parent_exit["exit_reason"])
            self.assertEqual(exits[0]["exit_price"], 100.7)
            self.assertNotIn(signal()["setup_id"], ba.active)

    def test_missing_quote_never_rejects_or_deletes_parent_trade(self):
        with tempfile.TemporaryDirectory() as root:
            parent = PaperOutcomeTracker(root)
            parent.register(signal())
            ba = BidAskRepricingTracker(root)
            ba.register_parent_entry(parent.active[signal()["setup_id"]], now=NOW)
            ba.update_quotes({}, NOW)
            self.assertIn(signal()["setup_id"], ba.pending_entries)
            status = json.loads(ba.status_path.read_text())
            self.assertFalse(status["parity_ok"])

            recovered = BidAskRepricingTracker(root)
            self.assertIn(signal()["setup_id"], recovered.pending_entries)

    def test_iocl1_name_preserves_existing_simulator(self):
        self.assertIs(IocL1PaperOutcomeTracker, BidAskPaperOutcomeTracker)


if __name__ == "__main__":
    unittest.main()
