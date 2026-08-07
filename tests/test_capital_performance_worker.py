import json
from pathlib import Path
import tempfile
import unittest

import reporting.capital_performance_worker as worker


class CapitalPerformanceWorkerTests(unittest.TestCase):
    def test_live_loader_preserves_entry_order_not_exit_order(self):
        with tempfile.TemporaryDirectory() as temp:
            ledger = Path(temp) / "paper_signal_outcomes.jsonl"
            old_ledger = worker.LEDGER
            worker.LEDGER = ledger

            try:
                rows = [
                    {"event_type": "PAPER_ENTRY", "setup_id": "C3|FIRST"},
                    {"event_type": "PAPER_ENTRY", "setup_id": "C3|SECOND"},
                    {"event_type": "PAPER_EXIT", "setup_id": "C3|SECOND"},
                    {"event_type": "PAPER_EXIT", "setup_id": "C3|FIRST"},
                ]
                ledger.write_text(
                    "".join(json.dumps(row) + "\n" for row in rows)
                )

                exits = worker.load_live_exits()
            finally:
                worker.LEDGER = old_ledger

            by_setup = {
                row["setup_id"]: row["entry_sequence"]
                for row in exits
            }
            self.assertEqual(by_setup["C3|FIRST"], 0)
            self.assertEqual(by_setup["C3|SECOND"], 1)



    def test_compaction_preserves_legacy_entry_timestamp_absence(self):
        row = {
            "setup_id": "C3|LEGACY",
            "strategy_id": "C3",
            "signal_timestamp": "2026-08-06T14:00:00+00:00",
            "entry_price": 10.0,
            "stop_price": 9.8,
            "exit_timestamp": "2026-08-06T14:05:00+00:00",
            "exit_price": 10.1,
        }

        compact = worker.compact_exit(row, 0)

        self.assertNotIn("entry_timestamp", compact)

    def test_compaction_preserves_explicit_never_entered_marker(self):
        row = {
            "setup_id": "O|NOENTRY",
            "strategy_id": "O",
            "entry_timestamp": None,
        }

        compact = worker.compact_exit(row, 0)

        self.assertIn("entry_timestamp", compact)
        self.assertIsNone(compact["entry_timestamp"])

if __name__ == "__main__":
    unittest.main()
