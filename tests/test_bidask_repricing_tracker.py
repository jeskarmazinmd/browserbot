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
            ba = BidAskRepricingTracker(root)

            self.assertTrue(parent.register(signal()))
            setup_id = signal()["setup_id"]

            self.assertTrue(
                ba.register_parent_entry(
                    parent.active[setup_id],
                    quote={"bid": 100.0, "ask": 100.1},
                    now=NOW,
                )
            )
            self.assertFalse(ba.pending_entries)
            self.assertIn(setup_id, ba.active)
            self.assertEqual(ba.active[setup_id]["entry_price"], 100.1)

            exit_time = NOW + timedelta(seconds=30)
            parent_exit = dict(
                parent.active[setup_id],
                exit_timestamp=exit_time.isoformat(),
                exit_price=100.5,
                exit_reason="STOP",
            )
            result = ba.register_parent_exits(
                [parent_exit],
                {"ABC": {"bid": 100.4, "ask": 100.5}},
                exit_time,
            )

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["exit_price"], 100.4)
            self.assertEqual(
                result[0]["exit_timestamp"],
                parent_exit["exit_timestamp"],
            )
            self.assertEqual(result[0]["exit_reason"], "STOP")
            self.assertEqual(
                result[0]["parent_exit_timestamp"],
                parent_exit["exit_timestamp"],
            )
            self.assertFalse(ba.pending_exits)
            self.assertNotIn(setup_id, ba.active)

    def test_missing_entry_quote_is_immediately_unpriced_and_never_recovered(self):
        with tempfile.TemporaryDirectory() as root:
            parent = PaperOutcomeTracker(root)
            parent.register(signal())
            ba = BidAskRepricingTracker(root)
            current = datetime.now(timezone.utc)
            setup_id = signal()["setup_id"]

            self.assertTrue(ba.register_parent_entry(
                parent.active[setup_id], now=current
            ))
            self.assertNotIn(setup_id, ba.pending_entries)
            self.assertNotIn(setup_id, ba.active)
            self.assertEqual(ba.quarantined_entries, 1)

            # A future quote must never retroactively price the entry.
            ba.update_quotes(
                {"ABC": {"bid": 99.9, "ask": 100.1}},
                current + timedelta(seconds=1),
            )
            self.assertNotIn(setup_id, ba.active)
            self.assertNotIn(setup_id, ba.seen_entries)

            status = json.loads(ba.status_path.read_text())
            self.assertEqual(status["pending_entries"], 0)
            self.assertEqual(
                status["paired_coverage"]["unpriced_entries"], 1
            )
            self.assertFalse(status["parity_ok"])

    def test_iocl1_name_preserves_existing_simulator(self):
        self.assertIs(IocL1PaperOutcomeTracker, BidAskPaperOutcomeTracker)

    def test_exit_uses_fresh_bid_when_ask_is_stale(self):
        with tempfile.TemporaryDirectory() as root:
            parent = PaperOutcomeTracker(root)
            parent.register(signal())
            tracker = BidAskRepricingTracker(root)
            setup_id = signal()["setup_id"]

            tracker.register_parent_entry(
                parent.active[setup_id],
                quote={"bid": 100.0, "ask": 100.1},
                now=NOW,
            )
            self.assertIn(setup_id, tracker.active)

            exit_time = NOW + timedelta(seconds=30)
            parent_exit = dict(
                parent.active[setup_id],
                exit_timestamp=exit_time.isoformat(),
                exit_price=100.4,
                exit_reason="STOP",
            )

            # Exit needs BID only.  ASK may be absent/stale without preventing
            # exact-cycle SELL@bid pricing.
            result = tracker.register_parent_exits(
                [parent_exit],
                {
                    "ABC": {
                        "bid": 100.3,
                        "bid_time_ms": exit_time.timestamp() * 1000,
                    }
                },
                exit_time,
            )

            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]["exit_bid"], 100.3)
            self.assertEqual(result[0]["exit_price"], 100.3)
            self.assertIsNone(result[0]["exit_ask"])
            self.assertEqual(
                result[0]["exit_timestamp"],
                parent_exit["exit_timestamp"],
            )

    def test_next_session_bid_quarantines_old_exit_without_pricing_it(self):
        with tempfile.TemporaryDirectory() as root:
            parent = PaperOutcomeTracker(root)
            parent.register(signal())
            tracker = BidAskRepricingTracker(root)
            setup_id = signal()["setup_id"]

            tracker.register_parent_entry(
                parent.active[setup_id],
                quote={"bid": 100.0, "ask": 100.1},
                now=NOW,
            )

            exit_time = NOW + timedelta(seconds=30)
            parent_exit = dict(
                parent.active[setup_id],
                exit_timestamp=exit_time.isoformat(),
                exit_price=100.4,
                exit_reason="STOP",
            )

            # No BID in the parent exit cycle => immediately unpriced.
            result = tracker.register_parent_exits(
                [parent_exit], {}, exit_time
            )
            self.assertEqual(result, [])
            self.assertNotIn(setup_id, tracker.active)
            self.assertFalse(tracker.pending_exits)
            self.assertEqual(tracker.quarantined_exits, 1)

            # A next-session/future BID cannot resurrect or price that exit.
            future = exit_time + timedelta(hours=18)
            tracker.update_quotes(
                {
                    "ABC": {
                        "bid": 101.0,
                        "bid_time_ms": future.timestamp() * 1000,
                    }
                },
                future,
            )
            self.assertNotIn(setup_id, tracker.seen_exits)

            ledger = (
                tracker.ledger_path.read_text()
                if tracker.ledger_path.exists()
                else ""
            )
            self.assertNotIn('"event_type":"BA_REPRICE_EXIT"', ledger)

            audit = json.loads(
                tracker.quarantine_path.read_text().splitlines()[-1]
            )
            self.assertEqual(
                audit["reason"],
                "exit_bid_unavailable_in_parent_cycle",
            )

    def test_missing_exit_bid_is_immediately_unpriced_and_never_recovered(self):
        with tempfile.TemporaryDirectory() as root:
            parent = PaperOutcomeTracker(root)
            parent.register(signal())
            tracker = BidAskRepricingTracker(root)
            setup_id = signal()["setup_id"]

            tracker.register_parent_entry(
                parent.active[setup_id],
                quote={"bid": 100.0, "ask": 100.1},
                now=NOW,
            )
            self.assertIn(setup_id, tracker.active)

            exit_time = NOW + timedelta(seconds=30)
            parent_exit = dict(
                parent.active[setup_id],
                exit_timestamp=exit_time.isoformat(),
                exit_price=100.4,
                exit_reason="STOP",
            )

            self.assertEqual(
                tracker.register_parent_exits([parent_exit], {}, exit_time),
                [],
            )
            self.assertNotIn(setup_id, tracker.pending_exits)
            self.assertNotIn(setup_id, tracker.active)
            self.assertEqual(tracker.quarantined_exits, 1)

            # Even one second later, a perfectly valid bid cannot be used.
            self.assertEqual(
                tracker.update_quotes(
                    {"ABC": {
                        "bid": 100.3,
                        "bid_time_ms": (
                            exit_time + timedelta(seconds=1)
                        ).timestamp() * 1000,
                    }},
                    exit_time + timedelta(seconds=1),
                ),
                [],
            )
            self.assertNotIn(setup_id, tracker.seen_exits)

            audit = json.loads(
                tracker.quarantine_path.read_text().splitlines()[-1]
            )
            self.assertEqual(
                audit["reason"],
                "exit_bid_unavailable_in_parent_cycle",
            )

    def test_restart_discards_legacy_pending_work_without_future_pricing(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = BidAskRepricingTracker(root)
            setup_id = "C3MG_I5S|ABC|legacy"
            legacy_entry = {
                "setup_id": setup_id,
                "strategy_id": "C3MG_I5S",
                "symbol": "ABC",
                "entry_price": 100.0,
                "entry_timestamp": NOW.isoformat(),
                "queued_at": NOW.isoformat(),
            }
            tracker._atomic_json(tracker.state_path, {
                "updated_at": NOW.isoformat(),
                "pending_entries": [legacy_entry],
                "pending_exits": [],
            })

            recovered = BidAskRepricingTracker(root)
            self.assertFalse(recovered.pending_entries)
            self.assertEqual(recovered.quarantined_entries, 1)

            recovered.update_quotes(
                {"ABC": {"bid": 99.9, "ask": 100.1}},
                NOW + timedelta(seconds=1),
            )
            self.assertNotIn(setup_id, recovered.active)
            self.assertNotIn(setup_id, recovered.seen_entries)

    def _runner_quote_provider(self, quote):
        # Extract only the quote provider so importing the production runner
        # cannot start unrelated integrations or require credentials.
        source = (
            Path(__file__).resolve().parents[1]
            / "live_strategy_runner.py"
        ).read_text()
        node = next(
            item for item in ast.parse(source).body
            if isinstance(item, ast.FunctionDef)
            and item.name == "_nh015_execution_quotes"
        )
        scope = {
            "time": time,
            "NH015_EXECUTION_QUOTE_MAX_AGE_SECONDS": 5.0,
            "append_bot_event": lambda *args, **kwargs: None,
        }
        response = types.SimpleNamespace(
            status_code=200,
            json=lambda: {
                "ABC": {
                    "realtime": True,
                    "quote": quote,
                }
            },
        )
        scope["_market_data_client"] = lambda: types.SimpleNamespace(
            get_quotes=lambda symbols: response
        )
        exec(
            compile(
                ast.Module(body=[node], type_ignores=[]),
                "provider",
                "exec",
            ),
            scope,
        )
        return scope["_nh015_execution_quotes"]

    def test_v3_accepts_old_displayed_ask_while_ioc_stays_strict(self):
        now_ms = time.time() * 1000
        provider = self._runner_quote_provider({
            "bidPrice": 99.9,
            "askPrice": 100.1,
            "bidTime": now_ms,
            "askTime": now_ms - 30_000,
            "quoteTime": now_ms,
        })

        live, v3 = provider(["ABC"], include_repricing=True)

        # IOC/live still rejects the stale two-sided execution quote.
        self.assertEqual(live, {})

        # V3 records the contemporaneously returned displayed ask.
        self.assertEqual(v3["ABC"]["ask"], 100.1)
        self.assertEqual(v3["ABC"]["bid"], 99.9)
        self.assertGreater(v3["ABC"]["ask_age_seconds"], 5.0)

    def test_v3_entry_ask_does_not_require_fresh_bid(self):
        now_ms = time.time() * 1000
        provider = self._runner_quote_provider({
            "bidPrice": 99.9,
            "askPrice": 100.1,
            "bidTime": now_ms - 30_000,
            "askTime": now_ms,
            "quoteTime": now_ms,
        })

        live, v3 = provider(["ABC"], include_repricing=True)

        self.assertEqual(live, {})
        self.assertEqual(v3["ABC"]["ask"], 100.1)
        self.assertGreater(v3["ABC"]["bid_age_seconds"], 5.0)

    def test_v3_exit_bid_does_not_require_fresh_ask(self):
        now_ms = time.time() * 1000
        provider = self._runner_quote_provider({
            "bidPrice": 99.9,
            "askPrice": 100.1,
            "bidTime": now_ms,
            "askTime": now_ms - 30_000,
            "quoteTime": now_ms,
        })

        live, v3 = provider(["ABC"], include_repricing=True)

        self.assertEqual(live, {})
        self.assertEqual(v3["ABC"]["bid"], 99.9)
        self.assertGreater(v3["ABC"]["ask_age_seconds"], 5.0)

    def test_v3_accepts_old_displayed_bid_for_exit(self):
        now_ms = time.time() * 1000
        provider = self._runner_quote_provider({
            "bidPrice": 99.9,
            "askPrice": 100.1,
            "bidTime": now_ms - 30_000,
            "askTime": now_ms,
            "quoteTime": now_ms,
        })

        live, v3 = provider(["ABC"], include_repricing=True)

        self.assertEqual(live, {})
        self.assertEqual(v3["ABC"]["bid"], 99.9)
        self.assertGreater(v3["ABC"]["bid_age_seconds"], 5.0)

    def test_v3_tracker_persists_quote_side_ages(self):
        with tempfile.TemporaryDirectory() as root:
            parent = PaperOutcomeTracker(root)
            parent.register(signal())

            tracker = BidAskRepricingTracker(root)
            setup_id = signal()["setup_id"]

            tracker.register_parent_entry(
                parent.active[setup_id],
                quote={
                    "ask": 100.1,
                    "ask_time_ms": 123456789.0,
                    "ask_age_seconds": 30.0,
                },
                now=NOW,
            )

            entry = tracker.active[setup_id]
            self.assertEqual(entry["entry_ask"], 100.1)
            self.assertEqual(entry["entry_ask_time_ms"], 123456789.0)
            self.assertEqual(entry["entry_ask_age_seconds"], 30.0)

            exit_time = NOW + timedelta(seconds=30)
            parent_exit = dict(
                parent.active[setup_id],
                exit_timestamp=exit_time.isoformat(),
                exit_price=100.4,
                exit_reason="STOP",
            )

            rows = tracker.register_parent_exits(
                [parent_exit],
                {
                    "ABC": {
                        "bid": 100.3,
                        "bid_time_ms": 123456999.0,
                        "bid_age_seconds": 45.0,
                    }
                },
                exit_time,
            )

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["exit_bid"], 100.3)
            self.assertEqual(rows[0]["exit_bid_time_ms"], 123456999.0)
            self.assertEqual(rows[0]["exit_bid_age_seconds"], 45.0)

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
