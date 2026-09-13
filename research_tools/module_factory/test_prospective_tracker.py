from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import tempfile
import unittest

from research_tools.module_factory.prospective_tracker import (
    FactoryProspectiveTracker,
)
from research_tools.module_factory.executable_quote_feed import ExecutableQuote


class FactoryProspectiveTrackerTests(unittest.TestCase):

    def tracker(self, root):
        root = Path(root)
        return FactoryProspectiveTracker(
            state_path=root / "active.json",
            outcomes_path=root / "outcomes.jsonl",
        )

    def start(self):
        return datetime(
            2026, 9, 3, 14, 0,
            tzinfo=timezone.utc,
        )

    def observe(
        self,
        tracker,
        *,
        strategy_id="FM_A",
        symbol="AAPL",
        direction=1,
        horizon=3,
        price=100.0,
    ):
        return tracker.observe_signal(
            strategy_id=strategy_id,
            symbol=symbol,
            timestamp=self.start(),
            entry_price=price,
            direction=direction,
            horizon=horizon,
            hypothesis_id=f"hypothesis:{strategy_id}",
            specification_hash=f"hash-{strategy_id}",
        )

    def test_long_closes_on_exact_processed_horizon(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = self.tracker(root)
            self.observe(tracker, horizon=3)

            self.assertEqual(
                tracker.consume_minute(
                    self.start() + timedelta(minutes=1),
                    {"AAPL": 101.0},
                ),
                (),
            )
            self.assertEqual(tracker.active_count, 1)

            self.assertEqual(
                tracker.consume_minute(
                    self.start() + timedelta(minutes=2),
                    {"AAPL": 102.0},
                ),
                (),
            )

            completed = tracker.consume_minute(
                self.start() + timedelta(minutes=3),
                {"AAPL": 103.0},
            )

            self.assertEqual(len(completed), 1)
            self.assertAlmostEqual(
                completed[0].return_pct,
                3.0,
            )

    def test_short_return_is_direction_adjusted(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = self.tracker(root)

            self.observe(
                tracker,
                strategy_id="FM_S",
                symbol="MSFT",
                direction=-1,
                horizon=2,
            )

            tracker.consume_minute(
                self.start() + timedelta(minutes=1),
                {"MSFT": 99.0},
            )

            completed = tracker.consume_minute(
                self.start() + timedelta(minutes=2),
                {"MSFT": 98.0},
            )

            self.assertAlmostEqual(
                completed[0].return_pct,
                2.0,
            )

    def test_same_minute_replay_does_not_advance_twice(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = self.tracker(root)
            self.observe(tracker, horizon=2)

            minute = self.start() + timedelta(minutes=1)

            tracker.consume_minute(
                minute,
                {"AAPL": 101.0},
            )

            tracker.consume_minute(
                minute,
                {"AAPL": 101.0},
            )

            completed = tracker.consume_minute(
                self.start() + timedelta(minutes=2),
                {"AAPL": 102.0},
            )

            self.assertEqual(len(completed), 1)

    def test_missing_symbol_does_not_advance(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = self.tracker(root)
            self.observe(tracker, horizon=2)

            tracker.consume_minute(
                self.start() + timedelta(minutes=1),
                {"MSFT": 200.0},
            )

            tracker.consume_minute(
                self.start() + timedelta(minutes=2),
                {"AAPL": 101.0},
            )

            self.assertEqual(
                tracker.active_count,
                1,
            )

            completed = tracker.consume_minute(
                self.start() + timedelta(minutes=3),
                {"AAPL": 102.0},
            )

            self.assertEqual(len(completed), 1)

    def test_restart_preserves_progress(self):
        with tempfile.TemporaryDirectory() as root:
            first = self.tracker(root)
            self.observe(first, horizon=2)

            first.consume_minute(
                self.start() + timedelta(minutes=1),
                {"AAPL": 101.0},
            )

            second = self.tracker(root)

            completed = second.consume_minute(
                self.start() + timedelta(minutes=2),
                {"AAPL": 102.0},
            )

            self.assertEqual(len(completed), 1)

    def test_duplicate_signal_is_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = self.tracker(root)

            self.assertTrue(
                self.observe(tracker)
            )
            self.assertFalse(
                self.observe(tracker)
            )

    def test_completed_signal_not_reopened(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = self.tracker(root)
            self.observe(tracker, horizon=1)

            tracker.consume_minute(
                self.start() + timedelta(minutes=1),
                {"AAPL": 101.0},
            )

            restarted = self.tracker(root)

            self.assertFalse(
                self.observe(
                    restarted,
                    horizon=1,
                )
            )

    def test_entry_minute_never_counts(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = self.tracker(root)
            self.observe(tracker, horizon=1)

            self.assertEqual(
                tracker.consume_minute(
                    self.start(),
                    {"AAPL": 105.0},
                ),
                (),
            )
            self.assertEqual(tracker.active_count, 1)

    def test_reconciles_durable_journal_idempotently(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            journal = root / "signals.jsonl"
            row = {
                "strategy_id": "FM_A", "symbol": "AAPL",
                "timestamp": self.start().isoformat(), "direction": 1,
                "horizon": 2,
                "data": {"hypothesis_id": "hypothesis:FM_A",
                         "specification_hash": "hash-FM_A"},
            }
            journal.write_text(json.dumps(row) + "\n")

            class Feed:
                def entry_price(self, **kwargs):
                    return 101.0

            first = self.tracker(root)
            self.assertEqual(first.reconcile_signal_journal(journal, Feed())["enrolled"], 1)
            restarted = self.tracker(root)
            self.assertEqual(restarted.reconcile_signal_journal(journal, Feed())["records"], 0)
            self.assertEqual(restarted.active_count, 1)

    def test_executable_quotes_use_bid_for_long_exit(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = self.tracker(root)
            self.observe(tracker, horizon=1, price=101.0)
            minute = self.start() + timedelta(minutes=1)
            quote = ExecutableQuote(
                symbol="AAPL", minute=minute, bid=102.0, ask=104.0
            )
            completed = tracker.consume_executable_minute(minute, {"AAPL": quote})
            self.assertEqual(len(completed), 1)
            self.assertAlmostEqual(completed[0].exit_price, 102.0)
            self.assertEqual(completed[0].execution_model, "BIDASK_EXEC_V1")


if __name__ == "__main__":
    unittest.main()
