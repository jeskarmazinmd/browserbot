from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from nh015_executable_shadow import NH015ExecutableShadow, SOURCE_STRATEGY_ID


class NH015ExecutableShadowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 9, 3, 15, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def signal(self):
        return {
            "strategy_id": SOURCE_STRATEGY_ID,
            "setup_id": f"{SOURCE_STRATEGY_ID}|XYZ|{self.now.isoformat()}",
            "symbol": "XYZ",
            "timestamp": self.now.isoformat(),
            "entry_price": 10.0,
            "target_price": 10.5,
            "stop_price": 9.5,
        }

    @staticmethod
    def quote(bid=9.98, ask=9.99):
        return {"bid": bid, "ask": ask, "spread_pct": 0.1}

    def test_marketable_limit_enters_at_ask_and_deduplicates(self):
        tracker = NH015ExecutableShadow(self.root)
        self.assertTrue(tracker.register(self.signal(), self.quote(), self.now))
        record = next(iter(tracker.active.values()))
        self.assertEqual(10.0, record["model_entry_price"])
        self.assertEqual(9.99, record["entry_price"])
        self.assertFalse(tracker.register(self.signal(), self.quote(), self.now))
        self.assertEqual(1, len(self.root.joinpath("nh015_exec_outcomes.jsonl").read_text().splitlines()))

    def test_ask_above_limit_is_durable_skip(self):
        tracker = NH015ExecutableShadow(self.root)
        self.assertFalse(tracker.register(self.signal(), self.quote(10.0, 10.01), self.now))
        row = json.loads(tracker.ledger_path.read_text())
        self.assertEqual("EXEC_SKIP", row["event_type"])
        self.assertEqual("ASK_ABOVE_LIMIT", row["reason"])
        restarted = NH015ExecutableShadow(self.root)
        self.assertEqual(1, restarted.skipped_ask_above_limit)
        self.assertFalse(restarted.register(self.signal(), self.quote(), self.now))

    def test_no_quote_is_deduplicated_after_restart(self):
        tracker = NH015ExecutableShadow(self.root)
        self.assertFalse(tracker.register(self.signal(), None, self.now))
        restarted = NH015ExecutableShadow(self.root)
        self.assertEqual(1, restarted.skipped_no_quote)
        self.assertFalse(restarted.register(self.signal(), self.quote(), self.now))

    def test_timer_starts_at_activation_not_entry(self):
        tracker = NH015ExecutableShadow(self.root)
        tracker.register(self.signal(), self.quote(), self.now)
        self.assertEqual([], tracker.update({"XYZ": self.quote(10.02, 10.03)}, self.now + timedelta(seconds=30)))
        self.assertEqual([], tracker.update({"XYZ": self.quote(10.03, 10.04)}, self.now + timedelta(seconds=40)))
        position = next(iter(tracker.active.values()))
        self.assertTrue(position["nh015_activated"])
        self.assertEqual([], tracker.update({"XYZ": self.quote(10.03, 10.04)}, self.now + timedelta(seconds=54)))
        closed = tracker.update({"XYZ": self.quote(10.03, 10.04)}, self.now + timedelta(seconds=55))
        self.assertEqual("NO_NEW_HIGH", closed[0]["exit_reason"])

    def test_new_high_resets_timer_and_survives_restart(self):
        tracker = NH015ExecutableShadow(self.root)
        tracker.register(self.signal(), self.quote(), self.now)
        tracker.update({"XYZ": self.quote(10.03, 10.04)}, self.now + timedelta(seconds=5))
        tracker.update({"XYZ": self.quote(10.10, 10.11)}, self.now + timedelta(seconds=15))
        restarted = NH015ExecutableShadow(self.root)
        self.assertEqual([], restarted.update({"XYZ": self.quote(10.09, 10.10)}, self.now + timedelta(seconds=29)))
        closed = restarted.update({"XYZ": self.quote(10.09, 10.10)}, self.now + timedelta(seconds=30))
        self.assertEqual("NO_NEW_HIGH", closed[0]["exit_reason"])

    def test_checkpoint_cannot_resurrect_completed_position(self):
        tracker = NH015ExecutableShadow(self.root)
        tracker.register(self.signal(), self.quote(), self.now)
        stale_checkpoint = tracker.state_path.read_text()
        tracker.update({"XYZ": self.quote(10.5, 10.51)}, self.now + timedelta(seconds=1))
        tracker.state_path.write_text(stale_checkpoint)
        restarted = NH015ExecutableShadow(self.root)
        self.assertEqual({}, restarted.active)
        self.assertEqual(1, restarted.completed)

    def test_stop_target_and_eod_use_bid(self):
        stop_tracker = NH015ExecutableShadow(self.root / "stop")
        stop_tracker.register(self.signal(), self.quote(), self.now)
        closed = stop_tracker.update({"XYZ": self.quote(9.49, 9.60)}, self.now + timedelta(seconds=1))
        self.assertEqual(("STOP", 9.49), (closed[0]["exit_reason"], closed[0]["exit_price"]))

        target_tracker = NH015ExecutableShadow(self.root / "target")
        target_tracker.register(self.signal(), self.quote(), self.now)
        closed = target_tracker.update({"XYZ": self.quote(10.5, 10.51)}, self.now + timedelta(seconds=1))
        self.assertEqual("TARGET", closed[0]["exit_reason"])

        eod_tracker = NH015ExecutableShadow(self.root / "eod")
        eod_tracker.register(self.signal(), self.quote(), self.now)
        eod = datetime(2026, 9, 3, 19, 55, tzinfo=timezone.utc)
        closed = eod_tracker.update({"XYZ": self.quote(10.1, 10.11)}, eod)
        self.assertEqual("EOD", closed[0]["exit_reason"])

    def test_production_runner_and_image_are_wired(self):
        project = Path(__file__).parents[1]
        runner = project.joinpath("live_strategy_runner.py").read_text()
        dockerfile = project.joinpath("Dockerfile").read_text()
        self.assertIn("from nh015_executable_shadow import NH015ExecutableShadow", runner)
        self.assertIn("set(positions) | nh015_exec_shadow.symbols()", runner)
        self.assertIn("nh015_exec_shadow.register(", runner)
        self.assertIn("nh015_exec_shadow.update(", runner)
        self.assertIn("COPY nh015_executable_shadow.py .", dockerfile)


if __name__ == "__main__":
    unittest.main()
