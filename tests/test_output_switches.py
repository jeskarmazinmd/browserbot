"""Disabling one paper output must not remove another module's signal."""

import json
import tempfile
import unittest
from pathlib import Path

from strategies.derived_runtime import derive_signals
from strategies.output_switches import PAUSED_BIDASK_PAPER_IDS, output_enabled


class OutputSwitchTests(unittest.TestCase):
    def test_source_output_off_keeps_derived_signal_available(self):
        parent = {
            "strategy_id": "B", "symbol": "XYZ",
            "timestamp": "2026-09-18T15:00:00+00:00",
            "setup_id": "B|XYZ|2026-09-18T15:00:00+00:00",
            "entry_price": 100.0, "target_price": 106.0,
            "stop_price": 98.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "switches.json"
            path.write_text(json.dumps({"B": False, "C4": True}))
            self.assertFalse(output_enabled("B", path))
            derived = derive_signals(parent)
            self.assertTrue(any(
                signal["strategy_id"] == "C4"
                and output_enabled(signal["strategy_id"], path)
                for signal in derived
            ))
            path.write_text(json.dumps({"B": True, "C4": False}))
            self.assertFalse(output_enabled("B", path))
            self.assertFalse(output_enabled("C4", path))

    def test_reviewed_paper_ids_and_report_suffix_are_paused(self):
        self.assertEqual(len(PAUSED_BIDASK_PAPER_IDS), 74)
        for strategy_id in PAUSED_BIDASK_PAPER_IDS:
            self.assertFalse(output_enabled(strategy_id))
            self.assertFalse(output_enabled(strategy_id + "BA"))
        self.assertTrue(output_enabled("C4"))
        self.assertTrue(output_enabled("C4BA"))
        self.assertTrue(output_enabled("C3N25S10NH015T1230BA"))


if __name__ == "__main__":
    unittest.main()
