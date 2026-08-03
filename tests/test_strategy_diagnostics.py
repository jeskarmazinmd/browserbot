import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from strategy_diagnostics import StrategyDiagnostics


class StrategyDiagnosticsTests(unittest.TestCase):
    def make_diagnostics(self, root):
        with patch.dict("os.environ", {"STRATEGY_DIAGNOSTICS_ROOT": root}):
            return StrategyDiagnostics()

    def test_records_evaluation_and_nearest_miss(self):
        with tempfile.TemporaryDirectory() as root:
            diagnostics = self.make_diagnostics(root)
            diagnostics.define("M1", "RUNNING", runtime_path="minute")
            diagnostics.evaluated(
                "M1", "2026-08-03T18:00:00+00:00", 2684,
                nearest_miss={"symbol": "XYZ", "failed_rules": ["rebound"]},
            )
            diagnostics.flush(force=True)
            row = json.loads(diagnostics.path.read_text())["modules"]["M1"]
            self.assertEqual(row["status"], "RUNNING")
            self.assertEqual(row["symbols_evaluated"], 2684)
            self.assertEqual(row["nearest_miss"]["symbol"], "XYZ")

    def test_waiting_parent_and_inactive_are_explicit(self):
        with tempfile.TemporaryDirectory() as root:
            diagnostics = self.make_diagnostics(root)
            diagnostics.parent_state("C1", "B", 0, 0)
            diagnostics.define("K1", "INACTIVE", reason="legacy")
            diagnostics.flush(force=True)
            modules = json.loads(diagnostics.path.read_text())["modules"]
            self.assertEqual(modules["C1"]["status"], "WAITING_PARENT")
            self.assertEqual(modules["K1"]["status"], "INACTIVE")

    def test_write_is_rate_limited(self):
        with tempfile.TemporaryDirectory() as root:
            diagnostics = self.make_diagnostics(root)
            diagnostics.define("M1", "RUNNING")
            self.assertTrue(diagnostics.flush(force=True))
            original = diagnostics.path.read_text()
            diagnostics.evaluated("M1", "later", 1)
            self.assertFalse(diagnostics.flush())
            self.assertEqual(diagnostics.path.read_text(), original)


if __name__ == "__main__":
    unittest.main()
