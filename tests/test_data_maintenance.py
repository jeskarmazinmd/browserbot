import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

import data_maintenance


class DataMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.after_eod = datetime(2026, 8, 4, 20, 5, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def write_status(self, active):
        (self.root / "paper_signal_status.json").write_text(json.dumps({"active": active}))

    def test_refuses_to_rotate_with_active_outcomes(self):
        self.write_status(1)
        ledger = self.root / "paper_signal_outcomes.jsonl"
        ledger.write_text("keep me\n")
        result = data_maintenance.run(self.root, self.after_eod)
        self.assertEqual(result["status"], "SKIPPED")
        self.assertEqual(ledger.read_text(), "keep me\n")

    def test_refuses_before_eod(self):
        self.write_status(0)
        before = datetime(2026, 8, 4, 19, 54, tzinfo=timezone.utc)
        result = data_maintenance.run(self.root, before)
        self.assertEqual(result["status"], "SKIPPED")
        self.assertIn("before EOD", result["reason"])

    def test_compacts_closed_outcomes_and_rotates_logs(self):
        self.write_status(0)
        setup = "A|XYZ|2026-08-04T15:00:00+00:00"
        entry = {
            "event_type": "PAPER_ENTRY", "setup_id": setup, "strategy_id": "A",
            "signal_timestamp": "2026-08-04T15:00:00+00:00", "entry_price": 10,
        }
        exit_row = {
            **entry, "event_type": "PAPER_EXIT", "exit_timestamp": "2026-08-04T15:05:00+00:00",
            "exit_price": 10.1, "exit_reason": "TARGET", "pnl": 10,
        }
        (self.root / "paper_signal_outcomes.jsonl").write_text(
            json.dumps(entry) + "\n" + json.dumps(exit_row) + "\n"
        )
        event = {"timestamp": "2026-08-04T15:00:00+00:00", "event_type": "SIGNAL", "strategy_id": "A"}
        event_text = (json.dumps(event) + "\n") * 3
        (self.root / "bot_events.jsonl").write_text(event_text)
        old_minimum = data_maintenance.MIN_ROTATE_BYTES
        data_maintenance.MIN_ROTATE_BYTES = 1
        try:
            result = data_maintenance.run(self.root, self.after_eod)
        finally:
            data_maintenance.MIN_ROTATE_BYTES = old_minimum
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual((self.root / "paper_signal_outcomes.jsonl").stat().st_size, 0)
        compact = next((self.root / "archive").glob("paper_trades.*.jsonl.gz"))
        with gzip.open(compact, "rt") as handle:
            rows = [json.loads(line) for line in handle]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["setup_id"], setup)
        event_archive = next((self.root / "archive").glob("bot_events.*.jsonl.gz"))
        with gzip.open(event_archive, "rt") as handle:
            self.assertEqual(handle.read(), event_text)

    def test_incomplete_outcome_ledger_aborts_without_deletion(self):
        self.write_status(0)
        ledger = self.root / "paper_signal_outcomes.jsonl"
        ledger.write_text(json.dumps({"event_type": "PAPER_ENTRY", "setup_id": "open"}) + "\n")
        with self.assertRaises(RuntimeError):
            data_maintenance.run(self.root, self.after_eod)
        self.assertTrue(ledger.exists())
        self.assertGreater(ledger.stat().st_size, 0)

    def test_eod_event_summary_includes_intraday_segments(self):
        self.write_status(0)
        event = {"timestamp": "2026-08-04T15:00:00+00:00", "event_type": "SIGNAL", "strategy_id": "A"}
        segment = self.root / "archive" / "intraday" / "2026-08-04" / "bot_events.segment.jsonl.gz"
        segment.parent.mkdir(parents=True)
        with gzip.open(segment, "wt") as handle:
            handle.write(json.dumps(event) + "\n")
            handle.write(json.dumps(event) + "\n")
        (self.root / "bot_events.jsonl").write_text(json.dumps(event) + "\n")
        old_minimum = data_maintenance.MIN_ROTATE_BYTES
        data_maintenance.MIN_ROTATE_BYTES = 1
        try:
            result = data_maintenance.run(self.root, self.after_eod)
        finally:
            data_maintenance.MIN_ROTATE_BYTES = old_minimum
        summary_path = Path(result["actions"]["bot_events.jsonl"]["summary"])
        summary = json.loads(summary_path.read_text())
        self.assertEqual(summary["rows"], 3)
        self.assertEqual(summary["event_counts_by_market_date"]["2026-08-04"]["SIGNAL"], 3)


if __name__ == "__main__":
    unittest.main()
