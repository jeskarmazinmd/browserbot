from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


class ClosedOutcomeImmutabilityTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.old_mode = os.environ.get("RUN_MODE")
        cls.old_run_id = os.environ.get("RUN_ID")
        os.environ["RUN_MODE"] = "REPLAY"
        os.environ["RUN_ID"] = "closed_outcome_immutability"
        sys.modules.pop("reporting.engine", None)
        cls.engine = importlib.import_module("reporting.engine")

    @classmethod
    def tearDownClass(cls):
        if cls.old_mode is None:
            os.environ.pop("RUN_MODE", None)
        else:
            os.environ["RUN_MODE"] = cls.old_mode

        if cls.old_run_id is None:
            os.environ.pop("RUN_ID", None)
        else:
            os.environ["RUN_ID"] = cls.old_run_id

    def test_closed_legacy_stop_cannot_become_later_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tapes = root / "tapes"
            tapes.mkdir()

            outcomes_path = root / "outcomes.jsonl"
            original = {
                "key": "A|legacy|AAA",
                "strategy_id": "A",
                "timestamp": "2026-08-03T14:00:00+00:00",
                "symbol": "AAA",
                "entry": 100.0,
                "target": 101.0,
                "stop": 95.0,
                "paper_notional": 1000.0,
                "status": "closed",
                "exit_time": "2026-08-03T14:05:00+00:00",
                "exit_price": 95.0,
                "exit_reason": "stop",
                "ret_pct": -5.0,
                "pnl_usd": -50.0,
                "mfe_pct": None,
                "mae_pct": None,
                "last_checked": "2026-08-03T14:05:00+00:00",
            }
            outcomes_path.write_text(json.dumps(original) + "\n")

            # A later, incomplete tape contains only a target price. The
            # historical stop must remain immutable.
            (tapes / "quotes_20260803.csv").write_text(
                "timestamp_utc,symbol,last_price\n"
                "2026-08-03T17:40:00+00:00,AAA,102.0\n"
            )

            self.engine.signal_paper_outcome_lines(
                [],
                strategy_id="A",
                outcomes_path=outcomes_path,
                tape_root=tapes,
            )

            saved = json.loads(outcomes_path.read_text().strip())

            self.assertEqual("closed", saved["status"])
            self.assertEqual("stop", saved["exit_reason"])
            self.assertEqual(95.0, saved["exit_price"])
            self.assertEqual(-5.0, saved["ret_pct"])
            self.assertEqual(-50.0, saved["pnl_usd"])
            self.assertEqual(
                "2026-08-03T14:05:00+00:00",
                saved["last_checked"],
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
