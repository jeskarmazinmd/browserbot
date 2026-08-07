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


if __name__ == "__main__":
    unittest.main()
