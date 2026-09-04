import json
from pathlib import Path
import tempfile
import unittest

import reporting.capital_performance_worker as worker


class CapitalPerformanceWorkerTests(unittest.TestCase):
    def setUp(self):
        self.old_paths = {
            "LEDGER": worker.LEDGER,
            "ARCHIVE": worker.ARCHIVE,
            "DUP_MODELS": worker.DUP_MODELS,
            "DUP_MODELS_TXT": worker.DUP_MODELS_TXT,
        }

    def tearDown(self):
        for name, value in self.old_paths.items():
            setattr(worker, name, value)

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

    def test_dup_model_report_contains_all_four_models(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            worker.LEDGER = root / "paper_signal_outcomes.jsonl"
            worker.ARCHIVE = root / "archive"
            worker.DUP_MODELS = root / "models.json"
            worker.DUP_MODELS_TXT = root / "models.txt"
            worker.ARCHIVE.mkdir()
            row = {
                "event_type": "PAPER_EXIT",
                "setup_id": f"{worker.DUP_STRATEGY_ID}|TEST|1",
                "strategy_id": worker.DUP_STRATEGY_ID,
                "signal_timestamp": "2026-09-03T14:00:00+00:00",
                "entry_price": 10.0,
                "stop_price": 9.9,
                "exit_timestamp": "2026-09-03T14:05:00+00:00",
                "exit_price": 10.1,
            }
            worker.LEDGER.write_text(
                json.dumps({"event_type": "PAPER_ENTRY", "setup_id": row["setup_id"]})
                + "\n" + json.dumps(row) + "\n"
            )

            payload = worker.update_dup_models()

            self.assertEqual(4, len(payload["models"]))
            self.assertIn("DUP_5K_DAILY", payload["models"])
            self.assertIn("DUP_10K_DAILY", payload["models"])
            self.assertIn("DUP_5K_ROLLING", payload["models"])
            self.assertIn("DUP_10K_ROLLING", payload["models"])
            self.assertIn("DUP_10K_ROLLING", worker.DUP_MODELS_TXT.read_text())

if __name__ == "__main__":
    unittest.main()
