import json
import gzip
from pathlib import Path
import tempfile
import unittest

from reporting.all_engine_performance import (
    calculate,
    equity_quote,
    last_gzip_json,
    options_rv_closed_pnl,
    simulate_slots,
)
import reporting.all_engine_performance_worker as worker


class AllEnginePerformanceTests(unittest.TestCase):
    def test_live_gzip_reader_keeps_complete_rows_when_tail_is_unfinished(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "live.jsonl.gz"
            compressed = gzip.compress(
                b'{"timestamp":"2026-08-11T18:00:00+00:00","value":1}\n'
                b'{"timestamp":"2026-08-11T18:01:00+00:00","value":2}\n'
            )
            path.write_bytes(compressed[:-4])

            self.assertEqual(last_gzip_json(path)["value"], 2)

    def test_equity_quote_uses_main_tape_fallback(self):
        marks = {"equity": {}, "main_last": {"EMBC": 5.01}}
        self.assertEqual(equity_quote("EMBC", marks)["bid"], 5.01)
        self.assertEqual(equity_quote("EMBC", marks)["source"], "main_last_fallback")

    def test_slot_simulation_skips_sixth_concurrent_trade(self):
        from datetime import datetime, timedelta, timezone
        opened = datetime(2026, 8, 11, 14, tzinfo=timezone.utc)
        trades = [
            {"opened": opened, "closed": opened + timedelta(hours=1),
             "pnl": 10.0, "id": str(index)}
            for index in range(6)
        ]
        result = simulate_slots(trades)
        self.assertEqual(result["taken"], 5)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["open_taken"], 0)
        self.assertEqual(result["closed_taken"], 5)
        self.assertAlmostEqual(result["return_pct"], 1.0)

    def test_slot_open_count_only_includes_admitted_trades(self):
        from datetime import datetime, timedelta, timezone
        opened = datetime(2026, 8, 11, 14, tzinfo=timezone.utc)
        trades = [
            {
                "opened": opened,
                "closed": opened + timedelta(hours=1),
                "pnl": 10.0,
                "id": str(index),
                "is_open": True,
            }
            for index in range(6)
        ]
        result = simulate_slots(trades)
        self.assertEqual(result["signals"], 6)
        self.assertEqual(result["taken"], 5)
        self.assertEqual(result["open_taken"], 5)
        self.assertEqual(result["closed_taken"], 0)
        self.assertEqual(result["open_taken"] + result["closed_taken"], result["taken"])

    def test_calculate_marks_swing_from_main_tape_fallback(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "tapes").mkdir()
            (root / "tapes" / "quotes_20260811.csv").write_text(
                "timestamp_utc,symbol,last_price\n"
                "2026-08-11T17:20:00+00:00,EMBC,5.01\n"
            )
            (root / "swing_paper_outcomes.jsonl").write_text(json.dumps({
                "event": "OPEN", "setup_id": "SWMOM2|EMBC|2026-08-11",
                "strategy_id": "SWMOM2", "symbol": "EMBC", "side": "LONG",
                "entry_price": 5.03, "shares": 198,
                "opened_at": "2026-08-11T14:00:42+00:00",
            }) + "\n")
            snapshot = calculate(
                root,
                day="2026-08-11",
                as_of=datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc),
            )
            self.assertAlmostEqual(snapshot["modules"]["SWMOM2"]["pnl"], -3.96)
            self.assertAlmostEqual(snapshot["modules"]["SWMOM2"]["return_pct"], -0.0792)
            self.assertEqual(snapshot["diagnostics"]["unmarked_by_engine"], {})

    def test_repairs_legacy_options_rv_closing_signs(self):
        row = {
            "opening_cash_flow": -993.3,
            "closing_cash_flow": -960.3,
            "exit_contract_sides": 2,
            "pnl_dollars": -1953.6,
        }
        # Correct closing cash flow is +957.70 after $1.30 commission.
        self.assertAlmostEqual(options_rv_closed_pnl(row), -35.6)

    def test_reports_core_bidask_shadow_separately(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "tapes").mkdir()
            (root / "tapes" / "quotes_20260811.csv").write_text(
                "timestamp_utc,symbol,last_price\n"
                "2026-08-11T17:20:00+00:00,XYZ,10.20\n"
            )
            rows = [
                {
                    "event_type": "PAPER_ENTRY", "setup_id": "one",
                    "strategy_id": "C3N25S10", "symbol": "XYZ",
                    "signal_timestamp": "2026-08-11T14:00:00+00:00",
                    "entry_timestamp": "2026-08-11T14:00:01+00:00",
                    "entry_price": 10.01, "notional": 100.10,
                },
                {
                    "event_type": "PAPER_EXIT", "setup_id": "one",
                    "strategy_id": "C3N25S10", "symbol": "XYZ",
                    "signal_timestamp": "2026-08-11T14:00:00+00:00",
                    "entry_timestamp": "2026-08-11T14:00:01+00:00",
                    "entry_price": 10.01, "notional": 100.10,
                    "exit_timestamp": "2026-08-11T14:05:00+00:00",
                    "exit_price": 10.11, "pnl": 1.0,
                },
            ]
            (root / "paper_signal_outcomes.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows)
            )
            (root / "paper_signal_v2_bidask_outcomes.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows)
            )
            repricing_rows = [
                {
                    **row,
                    "event_type": (
                        "BA_REPRICE_ENTRY"
                        if row["event_type"] == "PAPER_ENTRY"
                        else "BA_REPRICE_EXIT"
                    ),
                }
                for row in rows
            ]
            (root / "paper_signal_v3_bidask_repricing_outcomes.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in repricing_rows)
            )
            snapshot = calculate(
                root,
                day="2026-08-11",
                as_of=datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc),
            )
            self.assertEqual(
                snapshot["modules"]["C3N25S10BA"]["engine"],
                "main_bidask_repricing",
            )
            self.assertAlmostEqual(snapshot["modules"]["C3N25S10BA"]["pnl"], 1.0)
            self.assertEqual(
                snapshot["modules"]["C3N25S10IOCL1"]["engine"],
                "main_iocl1",
            )
            self.assertAlmostEqual(
                snapshot["modules"]["C3N25S10IOCL1"]["pnl"],
                1.0,
            )
            coverage = snapshot["diagnostics"]["bidask_paired_coverage"]
            self.assertTrue(coverage["parity_ok"])
            self.assertEqual(coverage["paired_entries"], 1)
            self.assertEqual(coverage["paired_exits"], 1)

    def test_reports_missing_bidask_twins_by_parent_setup_id(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "tapes").mkdir()
            (root / "tapes" / "quotes_20260811.csv").write_text(
                "timestamp_utc,symbol,last_price\n"
                "2026-08-11T17:20:00+00:00,XYZ,10.20\n"
            )
            parent = {
                "event_type": "PAPER_ENTRY", "setup_id": "missing-twin",
                "strategy_id": "C4", "symbol": "XYZ",
                "signal_timestamp": "2026-08-11T14:00:00+00:00",
                "entry_timestamp": "2026-08-11T14:00:00+00:00",
                "entry_price": 10.0, "notional": 1000.0,
            }
            (root / "paper_signal_outcomes.jsonl").write_text(
                json.dumps(parent) + "\n"
            )
            snapshot = calculate(
                root, day="2026-08-11",
                as_of=datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc),
            )
            coverage = snapshot["diagnostics"]["bidask_paired_coverage"]
            self.assertFalse(coverage["parity_ok"])
            self.assertEqual(
                coverage["missing_ba_entry_ids"], ["missing-twin"]
            )

    def test_reports_atomic_multi_leg_bidask_shadow_separately(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "tapes").mkdir()
            (root / "tapes" / "quotes_20260811.csv").write_text(
                "timestamp_utc,symbol,last_price\n"
            )
            entry = {
                "event_type": "MULTI_LEG_ENTRY", "group_id": "pair-one",
                "strategy_id": "PAIRMR1",
                "signal_timestamp": "2026-08-11T14:00:00+00:00",
                "group_notional": 1000,
                "legs": [
                    {"symbol": "AAA", "side": "LONG", "entry_price": 10,
                     "notional": 500, "last_price": 10},
                    {"symbol": "BBB", "side": "SHORT", "entry_price": 20,
                     "notional": 500, "last_price": 20},
                ],
            }
            exit_row = {
                **entry, "event_type": "MULTI_LEG_EXIT",
                "exit_timestamp": "2026-08-11T14:05:00+00:00",
                "pnl": 12.5,
            }
            (root / "multi_leg_paper_v2_bidask_outcomes.jsonl").write_text(
                json.dumps(entry) + "\n" + json.dumps(exit_row) + "\n"
            )
            snapshot = calculate(
                root,
                day="2026-08-11",
                as_of=datetime(2026, 8, 11, 18, 0, tzinfo=timezone.utc),
            )
            row = snapshot["modules"]["PAIRMR1BA"]
            self.assertEqual(row["engine"], "multi_leg_bidask")
            self.assertAlmostEqual(row["pnl"], 12.5)

    def test_accepts_fixed_options_rv_pnl(self):
        row = {
            "cash_flow_sign_version": 2,
            "pnl_dollars": -35.6,
        }
        self.assertAlmostEqual(options_rv_closed_pnl(row), -35.6)

    def test_history_is_immutable_after_first_finalization(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = (worker.ROOT, worker.LIVE_JSON, worker.LIVE_TXT,
                   worker.HISTORY_JSON, worker.HISTORY_TXT, worker.HEALTH)
            worker.ROOT = root
            worker.LIVE_JSON = root / "live.json"
            worker.LIVE_TXT = root / "live.txt"
            worker.HISTORY_JSON = root / "history.json"
            worker.HISTORY_TXT = root / "history.txt"
            worker.HEALTH = root / "health.json"
            (root / "tapes").mkdir()
            (root / "tapes" / "quotes_20260811.csv").write_text(
                "timestamp_utc,symbol,last_price\n"
            )
            original = worker.calculate
            calls = []
            def fake(*args, **kwargs):
                calls.append(None)
                return {"day": "2026-08-11", "as_of": "x", "module_count": 1,
                        "diagnostics": {"main_unmarked": 0, "unmarked_by_engine": {}},
                        "modules": {"A": {"return_pct": float(len(calls)), "engine": "main"}}}
            worker.calculate = fake
            try:
                now = datetime(2026, 8, 11, 21, 10, tzinfo=timezone.utc)
                worker.update_once(now)
                worker.update_once(now)
                history = json.loads(worker.HISTORY_JSON.read_text())
                self.assertEqual(history["days"]["2026-08-11"]["modules"]["A"]["return_pct"], 1.0)
            finally:
                worker.calculate = original
                (worker.ROOT, worker.LIVE_JSON, worker.LIVE_TXT,
                 worker.HISTORY_JSON, worker.HISTORY_TXT, worker.HEALTH) = old


if __name__ == "__main__":
    unittest.main()
