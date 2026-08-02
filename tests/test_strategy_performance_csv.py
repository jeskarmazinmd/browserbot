from __future__ import annotations

import csv
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class StrategyPerformanceCSVTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.old_mode = os.environ.get("RUN_MODE")
        cls.old_run_id = os.environ.get("RUN_ID")
        os.environ["RUN_MODE"] = "REPLAY"
        os.environ["RUN_ID"] = "strategy_performance_unittest"
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

    def test_comparison_starts_with_unified_architecture(self):
        self.assertEqual(
            "2026-08-03",
            self.engine.STRATEGY_PERFORMANCE_START_DATE,
        )

    def test_exactly_65_strategy_rows_and_30_snapshot_mappings(self):
        series = self.engine._strategy_signal_series_definitions()
        strategy_ids = [strategy_id for strategy_id, _ in series]
        independent_ids = set(self.engine.INDEPENDENT_STRATEGY_PATHS)

        self.assertEqual(65, len(series))
        self.assertEqual(65, len(set(strategy_ids)))
        self.assertEqual(30, len(independent_ids))
        self.assertTrue(
            {"GE1", "GM1", "GP1", "GR1", "GT1"}.issubset(
                independent_ids
            )
        )

    def test_csv_records_returns_and_multiday_comparison(self):
        engine = self.engine

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            csv_path = root / "strategy_performance.csv"
            table_path = root / "strategy_performance_table.txt"
            history_path = root / "daily_pnl_history.json"
            a_path = root / "a.jsonl"
            ge1_path = root / "ge1.jsonl"

            a_path.write_text(
                "\n".join(
                    json.dumps(record)
                    for record in [
                        {
                            "key": "A|AAA|historical",
                            "strategy_id": "A",
                            "symbol": "AAA",
                            "timestamp": "2026-07-31T14:00:00+00:00",
                            "status": "closed",
                            "paper_notional": 1000.0,
                            "pnl_usd": 7.00,
                            "ret_pct": 0.70,
                        },
                        {
                            "key": "A|AAA|today",
                            "strategy_id": "A",
                            "symbol": "AAA",
                            "timestamp": "2026-08-03T14:00:00+00:00",
                            "status": "closed",
                            "paper_notional": 1000.0,
                            "pnl_usd": 12.50,
                            "ret_pct": 1.25,
                        },
                    ]
                )
                + "\n"
            )

            ge1_path.write_text(
                "\n".join(
                    json.dumps(record)
                    for record in [
                        {
                            "key": "GE1|BBB|historical",
                            "strategy_id": "GE1",
                            "symbol": "BBB",
                            "timestamp": "2026-07-31T14:01:00+00:00",
                            "status": "closed",
                            "paper_notional": 1000.0,
                            "pnl_usd": -2.00,
                            "ret_pct": -0.20,
                        },
                        {
                            "key": "GE1|BBB|today",
                            "strategy_id": "GE1",
                            "symbol": "BBB",
                            "timestamp": "2026-08-03T14:01:00+00:00",
                            "status": "closed",
                            "paper_notional": 1000.0,
                            "pnl_usd": -5.00,
                            "ret_pct": -0.50,
                        },
                    ]
                )
                + "\n"
            )

            history_path.write_text(json.dumps({
                "2026-07-31": {
                    "A signal": 7.0,
                    "GE1 signal": -2.0,
                }
            }) + "\n")

            engine._PAPER_DAY_RECORD_CACHE.clear()

            with (
                patch.object(
                    engine,
                    "STRATEGY_PERFORMANCE_CSV",
                    csv_path,
                ),
                patch.object(
                    engine,
                    "STRATEGY_PERFORMANCE_TABLE_TXT",
                    table_path,
                ),
                patch.object(
                    engine,
                    "DAILY_PNL_HISTORY_JSON",
                    history_path,
                ),
                patch.object(
                    engine,
                    "STRATEGY_PERFORMANCE_START_DATE",
                    "2026-07-01",
                ),
                patch.object(
                    engine,
                    "SIGNAL_PAPER_OUTCOMES_JSONL",
                    a_path,
                ),
                patch.object(
                    engine,
                    "SIGNAL_PAPER_OUTCOMES_GE1_JSONL",
                    ge1_path,
                ),
            ):
                rows = engine.write_strategy_performance_csv(
                    "2026-08-03"
                )

            with csv_path.open(newline="") as source:
                csv_rows = list(csv.DictReader(source))

            by_strategy = {
                row["strategy_id"]: row
                for row in csv_rows
            }

            self.assertEqual(65, len(rows))
            self.assertEqual(65, len(csv_rows))
            self.assertEqual(
                12.5,
                float(by_strategy["A"]["today_pnl_per_1000"]),
            )
            self.assertEqual(
                100.0,
                float(by_strategy["A"]["win_rate_pct"]),
            )
            self.assertEqual(
                -5.0,
                float(by_strategy["GE1"]["today_pnl_per_1000"]),
            )
            self.assertEqual(
                7.0,
                float(
                    by_strategy["A"][
                        "2026-07-31_pnl_per_1000"
                    ]
                ),
            )
            self.assertEqual(
                -2.0,
                float(
                    by_strategy["GE1"][
                        "2026-07-31_pnl_per_1000"
                    ]
                ),
            )
            self.assertEqual(
                1,
                int(by_strategy["A"]["2026-07-31_trades"]),
            )
            self.assertEqual(
                1,
                int(by_strategy["GE1"]["2026-07-31_trades"]),
            )
            self.assertEqual(
                9.75,
                float(
                    by_strategy["A"][
                        "average_pnl_per_closed_trade"
                    ]
                ),
            )

            rendered = table_path.read_text()
            self.assertIn(
                "Daily cells show P/L / trades",
                rendered,
            )
            self.assertIn("+7.00/1", rendered)
            self.assertIn("+12.50/1", rendered)
            self.assertIn("-2.00/1", rendered)
            self.assertIn("-5.00/1", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
