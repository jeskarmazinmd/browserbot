"""Disabling one paper output must not remove another module's signal."""

import json
import tempfile
import unittest
from pathlib import Path

from strategies.derived_runtime import derive_signals
from strategies.output_switches import output_enabled


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
            path.write_text(json.dumps({"B": False, "C1": True}))
            self.assertFalse(output_enabled("B", path))
            derived = derive_signals(parent)
            self.assertTrue(any(
                signal["strategy_id"] == "C1"
                and output_enabled(signal["strategy_id"], path)
                for signal in derived
            ))
            path.write_text(json.dumps({"B": True, "C1": False}))
            self.assertTrue(output_enabled("B", path))
            self.assertFalse(output_enabled("C1", path))


if __name__ == "__main__":
    unittest.main()
