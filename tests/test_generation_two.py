import ast
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import Mock

from generation_one_paper_tracker import GenerationOneBidAskTracker
from generation_two_paper_tracker import GenerationTwoBidAskTracker, FILE_STEM
from reporting.all_engine_performance import calculate
from reporting.generation_two_performance import calculate_generation_two
from strategies import generation_one as g1, generation_two as g2, registry, manifest

NOW = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)


def signal(sid="G2PGCTL", setup="one", **updates):
    event = {"timestamp": NOW.isoformat(), "symbol": "XYZ", "flash_drop_pct": 1.4,
             "pre30_return_std_pct": .2, "pre_return_pct": 1., "pre_r2": .7,
             "target_price": 10.5, "flash_start_price": 10.5}
    row = g2.MODULES[sid].refresh_event_for_entry(event, 10.)
    row.update(setup_id=setup, **updates)
    return row


def quote(now=NOW, bid=9.99, ask=10.01, size=1000, **updates):
    row = {"bid": bid, "ask": ask, "bid_size_raw": size, "ask_size_raw": size,
           "bid_time_ms": now.timestamp() * 1000, "ask_time_ms": now.timestamp() * 1000,
           "realtime": True}
    row.update(updates)
    return row


class G2CatalogTests(unittest.TestCase):
    def test_bounded_registered_unique_paper_only_catalog(self):
        self.assertEqual(len(g2.IDS), 64)
        self.assertFalse(g2.IDS & g1.IDS)
        self.assertTrue(g2.IDS <= registry.flash_strategy_configs().keys())
        self.assertTrue(g2.IDS <= manifest.STRATEGY_MANIFEST.keys())
        for sid in g2.IDS:
            meta = g2.metadata(sid)
            self.assertEqual(meta["generation"], 2)
            self.assertTrue(meta["paper_only"])
            self.assertFalse(meta["config"]["live_order_placement"])
            self.assertIn(meta["comparison_id"], g2.IDS)
            json.dumps(meta, allow_nan=False)

    def test_no_duplicate_parameter_sets_within_family(self):
        for prefix in ("G2PG", "G2QV"):
            rows = []
            for spec in g2.CATALOG:
                if not spec.strategy_id.startswith(prefix):
                    continue
                params = copy.deepcopy(g2.metadata(spec.strategy_id)["parameters"])
                for key in ("strategy_id", "hypothesis", "comparison_id"):
                    del params[key]
                rows.append(json.dumps(params, sort_keys=True))
            self.assertEqual(len(rows), len(set(rows)))

    def test_catalog_and_admission_survive_mutated_g1_catalog(self):
        before = signal()
        with patch.object(g1, "CATALOG", ()), patch.dict(g1.MODULES, {}, clear=True):
            self.assertEqual(signal(), before)
            self.assertTrue(g2.MODULES["G2PGCTL"].accepts_flash(before, 12))

    def test_matched_controls_have_frozen_g1_admission_and_exits(self):
        for sid, old in (("G2PGCTL", "G1PGN1000"), ("G2QVCTL", "G1QVN1000")):
            event = signal(sid)
            old_event = g1.MODULES[old].refresh_event_for_entry({**event, "target_price": 10.5}, 10.)
            for key in ("target_price", "stop_price", "seconds", "required_gain_pct"):
                self.assertEqual(event.get(key), old_event.get(key))
            self.assertEqual(g2.executable_votes(sid, event, 10.01, 9.99),
                             g1.executable_votes(old, old_event, 10.01, 9.99))

    def test_metadata_is_defensive(self):
        meta = g2.metadata("G2PGS10")
        meta["parameters"]["rules"][0]["stop"] = .99
        self.assertEqual(g2.metadata("G2PGS10")["parameters"]["rules"][0]["stop"], .05)


class G2RoutingTests(unittest.TestCase):
    def test_real_runner_function_uses_only_g2_tracker_and_no_replay_credit(self):
        source = Path(__file__).resolve().parents[1] / "live_strategy_runner.py"
        tree = ast.parse(source.read_text())
        fn = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                  and node.name == "register_single_leg_paper")
        environment = {"RUN_MODE": "LIVE", "GENERATION_TWO_IDS": g2.IDS,
                       "GENERATION_ONE_IDS": g1.IDS, "generation_two_outcomes": Mock(),
                       "generation_one_outcomes": Mock(), "independent_ba_outcomes": Mock(),
                       "paper_outcomes": Mock(), "independent_l1": Mock(), "quote_source": Mock()}
        environment["independent_l1"].quotes.return_value = {"XYZ": quote()}
        environment["quote_source"].now.return_value = NOW
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), "exec"), environment)
        environment["register_single_leg_paper"](signal())
        environment["generation_two_outcomes"].register_signal.assert_called_once()
        environment["generation_one_outcomes"].register_signal.assert_not_called()
        environment["independent_ba_outcomes"].register_signal.assert_not_called()
        environment["RUN_MODE"] = "REPLAY"
        self.assertFalse(environment["register_single_leg_paper"](signal()))
        self.assertEqual(environment["generation_two_outcomes"].register_signal.call_count, 1)

    def test_rebound_volume_request_condition_skips_all_g2_ids(self):
        source = Path(__file__).resolve().parents[1] / "live_strategy_runner.py"
        tree = ast.parse(source.read_text())
        condition = next(node.test for node in ast.walk(tree) if isinstance(node, ast.If)
                         and "GENERATION_TWO_IDS" in ast.unparse(node.test)
                         and "LT65" in ast.unparse(node.test))
        code = compile(ast.Expression(body=condition), str(source), "eval")
        for sid in g2.IDS:
            self.assertFalse(eval(code, {"strategy_id": sid, "GENERATION_TWO_IDS": g2.IDS}))
        from strategies import generation_three
        self.assertTrue(eval(code, {"strategy_id": "G1PQG", "GENERATION_TWO_IDS": g2.IDS,
                                   "GENERATION_THREE_IDS": generation_three.ALL_IDS}))


class G2TrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.tracker = GenerationTwoBidAskTracker(self.root, now_provider=lambda: NOW)

    def tearDown(self):
        self.temp.cleanup()

    def reason(self):
        return json.loads(self.tracker.ledger_path.read_text().splitlines()[-1])["reason"]

    def test_own_births_and_ledger_do_not_touch_g1(self):
        old = GenerationOneBidAskTracker(self.root, now_provider=lambda: NOW)
        before = old.birth_path.read_bytes()
        self.assertTrue(self.tracker.register_signal(signal(), quote(), NOW))
        self.assertEqual(old.birth_path.read_bytes(), before)
        self.assertFalse(old.ledger_path.exists())
        self.assertNotEqual(self.tracker.birth_path, old.birth_path)
        restarted = GenerationTwoBidAskTracker(self.root, now_provider=lambda: NOW + timedelta(hours=1))
        self.assertEqual(restarted.births, self.tracker.births)
        for key in ("remaining_qty", "entry_price", "stop_price", "notional", "research_metadata"):
            self.assertEqual(restarted.active["one"][key], self.tracker.active["one"][key])
        self.assertFalse(restarted.register_signal(signal(), quote(), NOW))

    def test_future_stale_and_prebirth_signals_fail_closed(self):
        for seconds in (-1, 1, -121):
            self.assertFalse(self.tracker.register_signal(
                signal(setup=str(seconds), timestamp=(NOW + timedelta(seconds=seconds)).isoformat()), quote(), NOW))
            self.assertEqual(self.reason(), "outside_prospective_signal_window")

    def test_corrupt_births_fail_closed(self):
        self.tracker.birth_path.write_text("{")
        with self.assertRaises(ValueError):
            GenerationTwoBidAskTracker(self.root, now_provider=lambda: NOW)

    def test_both_sides_must_be_fresh_even_for_controls(self):
        for side in ("bid", "ask"):
            self.assertFalse(self.tracker.register_signal(
                signal(setup=side), quote(**{side + "_time_ms": (NOW - timedelta(seconds=6)).timestamp() * 1000}), NOW))
            self.assertEqual(self.reason(), "stale_or_future_quote")

    def test_spread_gate_uses_l1_not_signal_price(self):
        self.assertFalse(self.tracker.register_signal(signal("G2PGS10"), quote(), NOW))
        self.assertEqual(self.reason(), "g2_spread_above_limit")
        self.assertTrue(self.tracker.register_signal(signal("G2PGS10", "tight"), quote(bid=10., ask=10.005), NOW))
        self.assertEqual(self.tracker.active["tight"]["entry_price"], 10.005)

    def test_upside_gate_recomputed_at_ask(self):
        self.assertFalse(self.tracker.register_signal(signal("G2PGU200"), quote(ask=10.4, bid=10.39), NOW))
        self.assertEqual(self.reason(), "g2_insufficient_executable_upside")
        self.assertTrue(self.tracker.register_signal(signal("G2PGU200", "enough"), quote(), NOW))

    def test_target_distance_spread_multiple_is_opportunity_filter(self):
        self.assertFalse(self.tracker.register_signal(signal("G2PGE8"), quote(bid=9.99, ask=10.1), NOW))
        self.assertEqual(self.reason(), "g2_target_distance_below_spread_multiple")
        self.assertTrue(self.tracker.register_signal(signal("G2PGE8", "tight"), quote(), NOW))

    def test_cash_and_timestamped_book_consumption_survive_restart(self):
        self.assertTrue(self.tracker.register_signal(signal(), quote(size=30), NOW))
        self.assertEqual(self.tracker.active["one"]["filled_qty"], 30)
        restarted = GenerationTwoBidAskTracker(self.root, now_provider=lambda: NOW)
        self.assertFalse(restarted.register_signal(signal(setup="samebook"), quote(size=30), NOW))
        later = NOW + timedelta(seconds=1)
        self.assertTrue(restarted.register_signal(signal(setup="newbook", timestamp=later.isoformat()), quote(later, size=30), later))

    def test_ledger_recovers_fill_when_checkpoint_is_missing(self):
        self.assertTrue(self.tracker.register_signal(signal(), quote(size=30), NOW))
        self.tracker.state_path.unlink(missing_ok=True)
        self.tracker.liquidity_path.unlink(missing_ok=True)
        restarted = GenerationTwoBidAskTracker(self.root, now_provider=lambda: NOW)
        self.assertEqual(restarted.active["one"]["remaining_qty"], 30)
        self.assertAlmostEqual(restarted._cash_for("G2PGCTL", NOW)[1], 5000 - 30 * 10.01)
        self.assertFalse(restarted.register_signal(signal(setup="consumed"), quote(size=30), NOW))

    def test_one_symbol_guard_is_scoped_to_strategy(self):
        self.assertTrue(self.tracker.register_signal(signal("G2PGONE"), quote(), NOW))
        self.assertFalse(self.tracker.register_signal(signal("G2PGONE", "two"), quote(), NOW))
        self.assertEqual(self.reason(), "g2_symbol_already_open")
        self.assertTrue(self.tracker.register_signal(signal("G2QVONE", "q"), quote(), NOW))
        self.assertTrue(self.tracker.register_signal(signal("G2PGONE", "other", symbol="ABC"), quote(), NOW))

    def test_partial_exits_release_only_filled_cash_and_keep_guard(self):
        self.assertTrue(self.tracker.register_signal(signal("G2PGONE"), quote(), NOW))
        count = self.tracker.active["one"]["filled_qty"]
        later = NOW + timedelta(minutes=1)
        self.assertFalse(self.tracker.update_quotes({"XYZ": quote(later, bid=10.6, ask=10.61, size=10)}, later))
        self.assertEqual(self.tracker.active["one"]["remaining_qty"], count - 10)
        self.assertAlmostEqual(self.tracker._cash_for("G2PGONE", later)[1], 5000 - count * 10.01 + 106)
        self.assertFalse(self.tracker.register_signal(signal("G2PGONE", "guard", timestamp=later.isoformat()), quote(later), later))
        final = later + timedelta(seconds=1)
        self.assertEqual(len(self.tracker.update_quotes({"XYZ": quote(final, bid=10.6, ask=10.61)}, final)), 1)
        self.assertFalse(self.tracker.active)

    def test_total_stop_risk_limit_sizes_residual_budget(self):
        sid = "G2PGB1"
        for index in range(2):
            now = NOW + timedelta(seconds=index)
            self.assertTrue(self.tracker.register_signal(
                signal(sid, str(index), symbol=str(index), timestamp=now.isoformat()), quote(now), now))
        rows = list(self.tracker.active.values())
        risk = sum(row["remaining_qty"] * (row["entry_price"] - row["stop_price"]) for row in rows)
        self.assertLessEqual(risk, 50.)
        remaining = self.tracker.quantity_limit(sid, {"stop_price": .095}, .1, self.tracker._cash_for(sid, NOW)[1], 100)
        self.assertGreater(remaining, 0)
        self.assertLess(remaining, rows[0]["filled_qty"])
        self.assertFalse(self.tracker.register_signal(signal(sid, "four", symbol="four"), quote(), NOW))
        restarted = GenerationTwoBidAskTracker(self.root, now_provider=lambda: NOW)
        self.assertFalse(restarted.register_signal(signal(sid, "five", symbol="five"), quote(), NOW))

    def test_checkpoint_stop_and_reduced_target_exit_at_observed_bid(self):
        for sid, at, bid in (("G2PGK5", 300, 10.0), ("G2PGD2", 1, 9.79), ("G2PGT50", 1, 10.3)):
            self.assertTrue(self.tracker.register_signal(signal(sid, sid), quote(), NOW))
            now = NOW + timedelta(seconds=at)
            closes = self.tracker.update_quotes({"XYZ": quote(now, bid=bid, ask=bid + .01)}, now)
            row = next(row for row in closes if row["strategy_id"] == sid)
            self.assertEqual(row["exit_price"], bid)
            self.assertNotIn(sid, self.tracker.active)

    def test_output_switch_blocks_entries_but_drains_exits(self):
        path = self.root / "switches.json"
        with patch.dict("os.environ", {"STRATEGY_OUTPUT_SWITCHES_PATH": str(path)}):
            self.assertTrue(self.tracker.register_signal(signal(), quote(), NOW))
            path.write_text(json.dumps({"G2PGCTL": False}))
            self.assertFalse(self.tracker.register_signal(signal(setup="disabled"), quote(), NOW))
            later = NOW + timedelta(minutes=1)
            self.assertEqual(len(self.tracker.update_quotes({"XYZ": quote(later, bid=10.6, ask=10.61)}, later)), 1)

    def test_reports_actual_partial_fills_and_activates_64_rows(self):
        self.assertTrue(self.tracker.register_signal(signal(), quote(size=30), NOW))
        later = NOW + timedelta(minutes=1)
        self.tracker.update_quotes({"XYZ": quote(later, bid=10.6, ask=10.61, size=10)}, later)
        modules, diag = calculate_generation_two(self.root, "2026-10-05", later, {}, lambda symbol, marks: {"bid": 10.4})
        self.assertEqual(len(modules), 64)
        row = modules["G2PGCTLBA"]
        self.assertAlmostEqual(row["pnl"], 10 * 10.6 + 20 * 10.4 - 30 * 10.01)
        self.assertEqual(row["engine"], "generation_two_bidask_independent")
        self.assertEqual(diag["partial_exits"], 1)
        self.assertEqual(modules["G2QVCTLBA"]["status"], "no_entries")
        incomplete, diag = calculate_generation_two(self.root, "2026-10-05", later, {}, lambda symbol, marks: {})
        self.assertNotIn("G2PGCTLBA", incomplete)
        self.assertEqual(diag["unmarked"], 1)

    def test_all_engine_includes_g2_and_preserves_g1(self):
        old = GenerationOneBidAskTracker(self.root, now_provider=lambda: NOW)
        result = calculate(self.root, as_of=NOW)
        self.assertTrue({sid + "BA" for sid in g2.IDS} <= result["modules"].keys())
        self.assertTrue({sid + "BA" for sid in old.IDS} <= result["modules"].keys())
        self.assertIn("generation_two", result["diagnostics"])


if __name__ == "__main__":
    unittest.main()
