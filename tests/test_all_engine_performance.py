import json
from pathlib import Path
import tempfile
import unittest

from reporting.all_engine_performance import (
    calculate,
    equity_quote,
    options_rv_closed_pnl,
    simulate_slots,
)
import reporting.all_engine_performance_worker as worker


class AllEnginePerformanceTests(unittest.TestCase):
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
        self.assertAlmostEqual(result["return_pct"], 1.0)

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
