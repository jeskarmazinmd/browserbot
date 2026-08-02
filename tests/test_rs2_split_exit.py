from __future__ import annotations

import importlib
import math
import os
import sys
import unittest

import pandas as pd


class RS2SplitExitTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.old_mode = os.environ.get("RUN_MODE")
        cls.old_run_id = os.environ.get("RUN_ID")
        os.environ["RUN_MODE"] = "REPLAY"
        os.environ["RUN_ID"] = "rs2_split_unittest"
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

    @staticmethod
    def base_record():
        return {
            "strategy_id": "RS2",
            "entry": 100.00,
            "target": 100.90,
            "stop": 99.35,
            "paper_notional": 1000.0,
            "status": "open",
        }

    def test_half_target_half_sixty_minute_hold(self):
        start = pd.Timestamp("2026-08-03T14:00:00Z")
        rows = pd.DataFrame({
            "timestamp": [
                start,
                start + pd.Timedelta(minutes=10),
                start + pd.Timedelta(minutes=30),
                start + pd.Timedelta(minutes=60),
            ],
            "price": [100.00, 100.90, 100.50, 100.40],
        })
        record = self.base_record()

        self.engine._resolve_rs2_split_outcome(
            record,
            rows,
            start,
        )

        self.assertEqual("closed", record["status"])
        self.assertEqual(
            "target",
            record["standard_leg_exit_reason"],
        )
        self.assertEqual(
            "60_minute_hold",
            record["hold_leg_exit_reason"],
        )
        self.assertTrue(
            math.isclose(record["standard_leg_ret_pct"], 0.90)
        )
        self.assertTrue(
            math.isclose(record["hold_leg_ret_pct"], 0.40)
        )
        self.assertTrue(math.isclose(record["ret_pct"], 0.65))
        self.assertTrue(math.isclose(record["pnl_usd"], 6.50))

    def test_protective_stop_applies_to_both_halves(self):
        start = pd.Timestamp("2026-08-03T14:00:00Z")
        rows = pd.DataFrame({
            "timestamp": [
                start,
                start + pd.Timedelta(minutes=5),
            ],
            "price": [100.00, 99.20],
        })
        record = self.base_record()

        self.engine._resolve_rs2_split_outcome(
            record,
            rows,
            start,
        )

        self.assertEqual("closed", record["status"])
        self.assertEqual(
            "stop",
            record["standard_leg_exit_reason"],
        )
        self.assertEqual(
            "stop",
            record["hold_leg_exit_reason"],
        )
        self.assertTrue(math.isclose(record["ret_pct"], -0.65))
        self.assertTrue(math.isclose(record["pnl_usd"], -6.50))

    def test_open_hold_leg_is_marked_to_market(self):
        start = pd.Timestamp("2026-08-03T14:00:00Z")
        rows = pd.DataFrame({
            "timestamp": [
                start,
                start + pd.Timedelta(minutes=10),
                start + pd.Timedelta(minutes=30),
            ],
            "price": [100.00, 100.90, 100.40],
        })
        record = self.base_record()

        self.engine._resolve_rs2_split_outcome(
            record,
            rows,
            start,
        )

        self.assertEqual("open", record["status"])
        self.assertEqual(
            "target",
            record["standard_leg_exit_reason"],
        )
        self.assertIsNone(record["hold_leg_exit_reason"])
        self.assertTrue(
            math.isclose(record["current_return_pct"], 0.65)
        )
        self.assertTrue(
            math.isclose(record["current_pnl_usd"], 6.50)
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
