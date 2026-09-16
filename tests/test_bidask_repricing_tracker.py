import json
import ast
import sys
import tempfile
import time
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# The small review archive may omit dependencies used only by untouched legacy
# code. Use real project modules when available and local stubs only otherwise.
try:
    import executable_paper_engine  # noqa: F401
except ModuleNotFoundError:
    engine = types.ModuleType("executable_paper_engine")
    engine.EXECUTION_MODEL = "BIDASK_EXEC_V1"
    engine.classify_limit_order = lambda *args, **kwargs: None
    engine.executable_mark = lambda *args, **kwargs: None
    sys.modules["executable_paper_engine"] = engine

try:
    import strategies  # noqa: F401
except ModuleNotFoundError:
    strategies = types.ModuleType("strategies")
    strategies.strategy_o = types.SimpleNamespace()
    sys.modules["strategies"] = strategies

from bidask_paper_outcome_tracker import (
    BidAskRepricingTracker,
    CycleQuoteProvider,
    IocL1PaperOutcomeTracker,
    BidAskPaperOutcomeTracker,
    register_paired_single_leg_signal,
)
from paper_outcome_tracker import PaperOutcomeTracker


NOW = datetime(2026, 9, 11, 14, 31, tzinfo=timezone.utc)


def signal():
    return {
        "setup_id": "C3N25S10|ABC|2026-09-11T14:31:00+00:00",
        "strategy_id": "C3N25S10",
        "symbol": "ABC",
        "timestamp": NOW.isoformat(),
        "entry_price": 100.0,
        "target_price": 101.0,
        "stop_price": 99.0,
        "exit_model": "c3",
        "paper_notional": 1000.0,
    }


class BidAskRepricingTrackerTest(unittest.TestCase):
    def test_cycle_quote_provider_fetches_each_symbol_only_once(self):
        calls = []

        def provider(symbols):
            calls.append(list(symbols))
            return {
                symbol: {"bid": 99.9, "ask": 100.1}
                for symbol in symbols
                if symbol != "MISS"
            }

        cached = CycleQuoteProvider(provider)
        cached.reset()
        self.assertIn("ABC", cached(["ABC"]))
        self.assertIn("ABC", cached(["ABC"]))
        self.assertEqual(cached(["MISS"]), {})
        self.assertEqual(cached(["MISS"]), {})
        self.assertEqual(calls, [["ABC"], ["MISS"]])

    def test_pair_uses_processing_time_for_freshness_and_same_cached_quote(self):
        with tempfile.TemporaryDirectory() as root:
            parent = PaperOutcomeTracker(root)
            ba = BidAskRepricingTracker(root)
            ioc = IocL1PaperOutcomeTracker(root)
            processing_time = NOW + timedelta(minutes=7)
            quote_ms = processing_time.timestamp() * 1000.0
            calls = []

            def provider(symbols):
                calls.append(list(symbols))
                return {
                    "ABC": {
                        "bid": 99.9,
                        "ask": 100.1,
                        "bid_size_raw": 100,
                        "ask_size_raw": 100,
                        "bid_time_ms": quote_ms,
                        "ask_time_ms": quote_ms,
                        "realtime": True,
                    }
                }

            cached = CycleQuoteProvider(provider)
            cached.reset()
            self.assertTrue(register_paired_single_leg_signal(
                signal(),
                parent_tracker=parent,
                repricing_tracker=ba,
                ioc_tracker=ioc,
                quote_provider=cached,
                now_provider=lambda: processing_time,
            ))
            self.assertIn(signal()["setup_id"], ba.active)
            self.assertIn(signal()["setup_id"], ioc.active)
            self.assertEqual(ba.active[signal()["setup_id"]]["entry_ask"], 100.1)
            self.assertIsNotNone(
                ba.active[signal()["setup_id"]]["parent_recorded_at"]
            )
            self.assertEqual(ioc.entry_unknown, 0)
            self.assertEqual(calls, [["ABC"]])

    def test_only_accepted_parent_trade_is_registered_and_exit_is_copied(self):
        with tempfile.TemporaryDirectory() as root:
            parent = PaperOutcomeTracker(root)
            self.assertTrue(parent.register(signal()))
            parent_entry = parent.active[signal()["setup_id"]]

            ba = BidAskRepricingTracker(root)
            self.assertTrue(ba.register_parent_entry(parent_entry, now=NOW))
            self.assertEqual(set(ba.pending_entries), {signal()["setup_id"]})

            ba.update_quotes({"ABC": {"bid": 99.9, "ask": 100.1}}, NOW)
            entry = ba.active[signal()["setup_id"]]
            self.assertEqual(entry["entry_price"], 100.1)
            self.assertEqual(entry["entry_timestamp"], parent_entry["entry_timestamp"])
            self.assertEqual(entry["notional"], parent_entry["notional"])
            self.assertEqual(entry["trade_intent"]["trade_id"], signal()["setup_id"])
            self.assertEqual(
                entry["trade_intent"]["source_strategy_id"], "C3N25S10"
            )

            parent_exit = {
                **parent_entry,
                "exit_timestamp": "2026-09-11T14:37:12+00:00",
                "exit_reason": "ADAPTIVE_TRAIL",
                "exit_price": 100.8,
            }
            exits = ba.register_parent_exits(
                [parent_exit], {"ABC": {"bid": 100.7, "ask": 100.8}},
                datetime.fromisoformat(parent_exit["exit_timestamp"]),
            )
            self.assertEqual(len(exits), 1)
            self.assertEqual(exits[0]["exit_timestamp"], parent_exit["exit_timestamp"])
            self.assertEqual(exits[0]["exit_reason"], parent_exit["exit_reason"])
            self.assertEqual(exits[0]["exit_price"], 100.7)
            self.assertNotIn(signal()["setup_id"], ba.active)

    def test_missing_quote_never_rejects_or_deletes_parent_trade(self):
        with tempfile.TemporaryDirectory() as root:
            parent = PaperOutcomeTracker(root)
            parent.register(signal())
            ba = BidAskRepricingTracker(root)
            current = datetime.now(timezone.utc)
            ba.register_parent_entry(
                parent.active[signal()["setup_id"]], now=current
            )
            ba.update_quotes({}, current)
            self.assertIn(signal()["setup_id"], ba.pending_entries)
            status = json.loads(ba.status_path.read_text())
            self.assertFalse(status["parity_ok"])

            recovered = BidAskRepricingTracker(root)
            self.assertIn(signal()["setup_id"], recovered.pending_entries)

    def test_iocl1_name_preserves_existing_simulator(self):
        self.assertIs(IocL1PaperOutcomeTracker, BidAskPaperOutcomeTracker)

    def test_exit_uses_fresh_bid_when_ask_is_stale(self):
        with tempfile.TemporaryDirectory() as root:
            parent = PaperOutcomeTracker(root)
            parent.register(signal())
            tracker = BidAskRepricingTracker(root)
            tracker.register_parent_entry(parent.active[signal()["setup_id"]], now=NOW)
            tracker.update_quotes({"ABC": {"ask": 100.1}}, NOW)
            exited = NOW + timedelta(seconds=30)
            parent_exit = dict(parent.active[signal()["setup_id"]],
                               exit_timestamp=exited.isoformat(), exit_price=100.4)
            result = tracker.register_parent_exits(
                [parent_exit], {"ABC": {"bid": 100.2, "bid_time_ms": exited.timestamp() * 1000}}, exited
            )
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["exit_bid_time_ms"], exited.timestamp() * 1000)
            self.assertEqual(result[0]["exit_resolution_delay_seconds"], 0)

    def test_next_session_bid_quarantines_old_exit_without_pricing_it(self):
        with tempfile.TemporaryDirectory() as root:
            parent = PaperOutcomeTracker(root)
            parent.register(signal())
            tracker = BidAskRepricingTracker(root)
            tracker.register_parent_entry(parent.active[signal()["setup_id"]], now=NOW)
            tracker.update_quotes({"ABC": {"ask": 100.1}}, NOW)
            exit_time = NOW + timedelta(seconds=30)
            parent_exit = dict(parent.active[signal()["setup_id"]],
                               exit_timestamp=exit_time.isoformat(), exit_price=100.4)
            tracker.register_parent_exits([parent_exit], {}, exit_time)
            next_day = exit_time + timedelta(days=1)
            self.assertEqual(tracker.update_quotes({"ABC": {
                "bid": 120, "bid_time_ms": next_day.timestamp() * 1000,
            }}, next_day), [])
            self.assertFalse(tracker.pending_exits)
            self.assertEqual(tracker.quarantined_exits, 1)
            self.assertNotIn("BA_REPRICE_EXIT\"", tracker.ledger_path.read_text())
            audit = json.loads(tracker.quarantine_path.read_text().splitlines()[-1])
            self.assertEqual(audit["reason"], "exit_bid_unavailable_within_120_seconds")

    def test_restart_preserves_exit_within_grace_and_expires_later(self):
        with tempfile.TemporaryDirectory() as root:
            current = datetime.now(timezone.utc)
            tracker = BidAskRepricingTracker(root)
            setup = "C3MG_I5S|ABC|recent"
            tracker.active[setup] = {
                "setup_id": setup, "strategy_id": "C3MG_I5S", "symbol": "ABC",
                "entry_price": 100.1, "notional": 1000,
            }
            tracker._append({"event_type": "BA_REPRICE_ENTRY", **tracker.active[setup]})
            exit_at = current - timedelta(seconds=90)
            tracker.pending_exits[setup] = {
                **tracker.active[setup], "exit_timestamp": exit_at.isoformat(),
            }
            tracker._write_status()
            recovered = BidAskRepricingTracker(root)
            self.assertIn(setup, recovered.pending_exits)
            recovered.update_quotes({"ABC": {
                "bid": 100.0, "bid_time_ms": current.timestamp() * 1000,
            }}, current)
            self.assertIn(setup, recovered.seen_exits)

    def test_live_quote_filter_stays_strict_while_v3_gets_bid(self):
        # Extract just the provider: importing the runner starts unrelated
        # production integrations and requires credentials.
        source = (Path(__file__).resolve().parents[1] / "live_strategy_runner.py").read_text()
        node = next(item for item in ast.parse(source).body
                    if isinstance(item, ast.FunctionDef) and item.name == "_nh015_execution_quotes")
        scope = {
            "time": time,
            "NH015_EXECUTION_QUOTE_MAX_AGE_SECONDS": 5.0,
            "append_bot_event": lambda *args, **kwargs: None,
        }
        now_ms = time.time() * 1000
        response = types.SimpleNamespace(status_code=200, json=lambda: {
            "ABC": {"realtime": True, "quote": {
                "bidPrice": 99.9, "askPrice": 100.1,
                "bidTime": now_ms, "askTime": now_ms - 30000,
                "quoteTime": now_ms,
            }}
        })
        scope["_market_data_client"] = lambda: types.SimpleNamespace(get_quotes=lambda symbols: response)
        exec(compile(ast.Module(body=[node], type_ignores=[]), "provider", "exec"), scope)
        live, v3 = scope["_nh015_execution_quotes"](["ABC"], include_repricing=True)
        self.assertEqual(live, {})
        self.assertEqual(v3["ABC"]["bid"], 99.9)
        self.assertNotIn("ask", v3["ABC"])

    def test_quote_batches_preserve_partial_results_and_prioritize_pending_exits(self):
        source = (Path(__file__).resolve().parents[1] / "live_strategy_runner.py").read_text()
        node = next(item for item in ast.parse(source).body
                    if isinstance(item, ast.FunctionDef) and item.name == "_nh015_execution_quotes")
        calls, errors = [], []
        now_ms = time.time() * 1000
        def get_quotes(symbols):
            calls.append(symbols)
            if "S101" in symbols:
                return types.SimpleNamespace(status_code=400)
            return types.SimpleNamespace(status_code=200, json=lambda: {
                symbol: {"realtime": True, "quote": {
                    "bidPrice": 10, "askPrice": 10.1,
                    "bidTime": now_ms, "askTime": now_ms,
                }} for symbol in symbols
            })
        scope = {
            "time": time,
            "NH015_EXECUTION_QUOTE_MAX_AGE_SECONDS": 5.0,
            "append_bot_event": lambda *args, **kwargs: errors.append((args, kwargs)),
            "_market_data_client": lambda: types.SimpleNamespace(get_quotes=get_quotes),
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), "provider", "exec"), scope)
        provider = scope["_nh015_execution_quotes"]
        symbols = [f"S{n:03d}" for n in range(450)]
        live, v3 = provider(symbols, include_repricing=True, priority_symbols=["S449"])
        self.assertEqual([len(batch) for batch in calls], [100, 100, 100, 100])
        self.assertIn("S449", calls[0])
        self.assertNotIn("S101", live)
        self.assertIn("S449", v3)
        self.assertTrue(errors)
        first = {symbol for batch in calls for symbol in batch}
        calls.clear()
        provider(symbols, include_repricing=True, priority_symbols=["S449"])
        second = {symbol for batch in calls for symbol in batch}
        self.assertIn("S449", second)
        self.assertEqual(len(first | second), 450)


if __name__ == "__main__":
    unittest.main()
