import copy
from datetime import datetime, timedelta, timezone
import importlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from engine.events import MarketSnapshot, Quote
from generation_one_paper_tracker import GenerationOneBidAskTracker, IDS, FILE_STEM
from strategies import generation_one as g, generation_one_minute as m
from strategies import pt325315_research as pt, qv425_research as qv, strategy_pmid
from strategies import registry, manifest
from reporting.all_engine_performance import calculate

NOW = datetime(2026, 10, 1, 16, 30, tzinfo=timezone.utc)


def event(**updates):
    row = {"timestamp": NOW.isoformat(), "symbol": "XYZ", "flash_drop_pct": 1.4,
           "pre30_return_std_pct": .2, "pre_return_pct": 1.0, "pre_r2": .7,
           "target_price": 10.5, "flash_start_price": 10.5}
    row.update(updates)
    return row


def signal(sid="G1PQG", setup="one", **updates):
    row = g.MODULES[sid].refresh_event_for_entry(event(), 10.0)
    row.update(setup_id=setup, **updates)
    return row


def quote(now=NOW, bid=9.99, ask=10.01, size=1000, **updates):
    row = {"bid": bid, "ask": ask, "bid_size_raw": size, "ask_size_raw": size,
           "bid_time_ms": now.timestamp() * 1000, "ask_time_ms": now.timestamp() * 1000,
           "realtime": True}
    row.update(updates)
    return row


def snapshot(now, price):
    return MarketSnapshot(now, {"SPY": Quote(price)}, 1, 1, 0)


class GenerationOneSignalsTests(unittest.TestCase):
    def test_catalog_is_bounded_disjoint_registered_and_paper_only(self):
        self.assertEqual(len(IDS), 51)
        self.assertFalse(g.IDS & m.IDS)
        self.assertTrue(g.IDS <= set(registry.flash_strategy_configs()))
        self.assertTrue(m.IDS <= {strategy.name for strategy in registry.MINUTE_STRATEGIES})
        self.assertTrue(IDS <= set(manifest.STRATEGY_MANIFEST))
        for sid in IDS:
            meta = g.metadata(sid) if sid in g.IDS else m.metadata(sid)
            self.assertTrue(meta["paper_only"])
            self.assertFalse(meta["config"]["live_order_placement"])
            self.assertEqual(meta["generation"], 1)
            self.assertEqual(meta["source_commit"], g.SOURCE_COMMIT)
            self.assertTrue(meta["source_strategy_ids"])
            self.assertTrue(meta["description"])
            json.dumps(meta, allow_nan=False)

    def test_frozen_raw_rules_match_source_boundaries(self):
        rng = random.Random(71)
        rules = (g.P_GAIN, g.P_TARGET, g.P_LOW, g.P_STOP, g.Q_QUALITY, g.Q_STOP, g.Q_BAND, g.Q_UP, g.MIDDAY)
        for _ in range(150):
            row = event(flash_drop_pct=rng.choice((.99, 1.0, 1.4, 12, 12.01)),
                        pre_return_pct=rng.choice((.74, .75, 1)), pre_r2=rng.choice((.49, .5, .8)),
                        target_price=rng.choice((3.24, 3.25, 8, 31.5, 31.51)),
                        pre30_return_std_pct=rng.choice((0, .1, .2, .4)))
            for rule in rules:
                expected = (strategy_pmid.accepts_flash(row, 12) if rule.kind == "M" else
                            pt.accepts(rule.source, row, 12) if rule.kind == "P" else
                            qv.accepts(rule.source, row, 12))
                self.assertEqual(g.raw_vote(rule, row, 12), expected, (rule.source, row))

    def test_frozen_exit_policies_match_selected_sources(self):
        for rule in (g.P_GAIN, g.P_TARGET, g.P_LOW, g.P_STOP, g.Q_QUALITY, g.Q_STOP, g.Q_BAND, g.Q_UP):
            source = pt if rule.kind == "P" else qv
            expected = source.refresh(rule.source, event(), 10.0)
            spec = g.Experiment("temporary", "test", (rule,), 1, rule)
            with patch.object(g, "CATALOG", (spec,)):
                actual = g.FrozenFlashModule("temporary").refresh_event_for_entry(event(), 10.0)
            for key in ("target_price", "stop_price", "stop_loss_fraction", "seconds", "mode", "required_gain_pct"):
                self.assertEqual(actual.get(key), expected.get(key), (rule.source, key))

    def test_mutating_sources_and_source_specs_cannot_change_any_child(self):
        before = {sid: (mod.accepts_flash(event(), 12), mod.refresh_event_for_entry(event(), 10))
                  for sid, mod in g.MODULES.items()}
        with patch.dict(pt.SPECS, {}, clear=True), patch.dict(qv.SPECS, {}, clear=True), \
             patch.object(pt.parent, "accepts_flash", side_effect=AssertionError("source called")), \
             patch.object(qv.parent, "CONFIG", {"stop_loss_fraction": .99}), \
             patch.object(strategy_pmid, "validate_confirmed_entry", side_effect=AssertionError("source called")):
            after = {sid: (mod.accepts_flash(event(), 12), mod.refresh_event_for_entry(event(), 10))
                     for sid, mod in g.MODULES.items()}
        self.assertEqual(before, after)

    def test_real_source_file_removal_leaves_registry_and_manifest_functional(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            shutil.copytree(root / "strategies", Path(temp) / "strategies", ignore=shutil.ignore_patterns("__pycache__"))
            for name in ("strategy_pt325315", "strategy_qv425", "strategy_pmid", "strategy_trendx2", "strategy_brk20", "pt325315_research", "qv425_research"):
                (Path(temp) / "strategies" / (name + ".py")).unlink()
            code = """
import sys
sys.path.insert(0, sys.argv[1])
from strategies import generation_one as g, generation_one_minute as m, registry, manifest
assert g.IDS <= set(registry.flash_strategy_configs())
assert m.IDS <= {s.name for s in registry.MINUTE_STRATEGIES}
assert g.IDS | m.IDS <= set(manifest.STRATEGY_MANIFEST)
e={'flash_drop_pct':1.4,'pre_return_pct':1,'pre_r2':.7,'target_price':10.5,'pre30_return_std_pct':.2,'timestamp':'2026-10-01T16:30:00+00:00'}
assert g.MODULES['G1PQG'].accepts_flash(e,12)
assert g.MODULES['G1PQG'].validate_confirmed_entry(g.MODULES['G1PQG'].refresh_event_for_entry(e,10),.2)==(True,None)
"""
            result = subprocess.run([sys.executable, "-c", code, temp], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            # Removing only old family files must also work with parent files
            # still present; those families are the selected source ID owners.
            for name in ("strategy_pt325315", "strategy_qv425", "strategy_pmid", "strategy_trendx2", "strategy_brk20"):
                shutil.copy2(root / "strategies" / (name + ".py"), Path(temp) / "strategies" / (name + ".py"))
            result = subprocess.run([sys.executable, "-c", code, temp], cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pruning_and_disabling_all_sources_leaves_children_enabled(self):
        import strategies.pruning as pruning
        sources = frozenset(rule.source for spec in g.CATALOG for rule in spec.rules) | {"TRENDX2", "BRK20"}
        with patch.object(pruning, "PRUNED_OUTPUT_STRATEGY_IDS", sources), tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "switches.json"
            path.write_text(json.dumps({sid: False for sid in sources}))
            with patch.dict("os.environ", {"STRATEGY_OUTPUT_SWITCHES_PATH": str(path)}):
                tracker = GenerationOneBidAskTracker(temp, now_provider=lambda: NOW)
                self.assertTrue(tracker.register_signal(signal(), quote(), NOW))
                path.write_text(json.dumps({"G1PQG": False}))
                self.assertFalse(tracker.register_signal(signal(setup="two"), quote(), NOW))
                self.assertTrue(tracker.update_quotes({"XYZ": quote(NOW + timedelta(minutes=1), bid=10.6, ask=10.62)}, NOW + timedelta(minutes=1)))

    def test_source_metadata_and_configs_are_defensive_copies(self):
        meta = g.metadata("G1PQG")
        meta["parameters"]["rules"][0]["stop"] = .99
        meta["config"]["stop_loss_fraction"] = .99
        self.assertEqual(g.MODULES["G1PQG"].CONFIG["stop_loss_fraction"], .05)
        self.assertEqual(g.metadata("G1PQG")["parameters"]["rules"][0]["stop"], .05)

    def test_voting_and_union_are_deduplicated_and_count_only_valid_gates(self):
        row = signal()
        self.assertEqual(len(g.executable_votes("G1PQ3", row, 10.01, 9.99)), 3)
        wide = g.executable_votes("G1PQU", row, 10.01, 9.9)
        self.assertEqual(wide, ("PT315G1525",))
        outside = signal(timestamp=NOW.replace(hour=14).isoformat())
        self.assertEqual(len(g.executable_votes("G1PQ3", outside, 10.01, 9.99)), 2)
        self.assertEqual(len(g.executable_votes("G1PQ34", row, 10.01, 9.99)), 4)
        hybrid = {**row, "frozen_trend_vote": True,
                  "frozen_trend_timestamp": (NOW - timedelta(minutes=1)).isoformat()}
        # Q's 3% stop cannot contribute an executable vote if already crossed,
        # even though the composite's uniform P stop is still intact.
        self.assertEqual(g.executable_votes("G1PQT3", hybrid, 10.01, 9.65),
                         ("PT315T75", "TRENDX2"))

    def test_birth_before_creation_has_no_signal_credit(self):
        row = signal(timestamp="2026-09-29T16:30:00+00:00")
        self.assertEqual(g.MODULES["G1PQG"].validate_confirmed_entry(row, .2), (False, "before_prospective_start"))

    def test_minute_predicates_match_frozen_sources_on_same_history(self):
        trend = importlib.import_module("strategies.strategy_trendx2")
        brk = importlib.import_module("strategies.strategy_brk20")
        rng = random.Random(23)
        for sid, source in (("G1TN500", trend), ("G1BN500", brk)):
            child = getattr(m, sid + "Strategy")()
            parent = source.Strategy()
            price = 100.0
            for index in range(100):
                price *= 1 + rng.choice((-.001, .0005, .0015))
                snap = snapshot(NOW + timedelta(minutes=index), price)
                expected, actual = parent.on_snapshot(snap), child.on_snapshot(snap)
                self.assertEqual(bool(actual), bool(expected), (sid, index))
                if expected:
                    self.assertEqual(actual[0].symbol, expected[0].symbol)
                    self.assertEqual(actual[0].data["target_price"], expected[0].data["target_price"])

    def test_minute_consensus_union_positive_and_gap_boundaries(self):
        consensus, union = m.G1TB2Strategy(), m.G1TBUStrategy()
        prices = [100 * (1.0005 ** index) for index in range(30)] + [102.0]
        for index, price in enumerate(prices):
            snap = snapshot(NOW + timedelta(minutes=index), price)
            a, b = consensus.on_snapshot(snap), union.on_snapshot(snap)
        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 1)
        self.assertEqual(a[0].data["constituent_votes"], ["TRENDX2", "BRK20"])
        self.assertEqual(consensus.on_snapshot(snap), [])
        self.assertEqual(consensus.on_snapshot(snapshot(NOW + timedelta(minutes=33), 103)), [])
        self.assertEqual(len(consensus._history["SPY"]), 1)

    def test_hybrid_trend_vote_is_owned_fresh_and_gap_sensitive(self):
        import pandas as pd
        from strategies.generation_one_market import enrich_confirmation
        end = NOW.replace(second=0) - timedelta(minutes=1)
        frame = pd.DataFrame([{"symbol": "SPY", "timestamp": end - timedelta(minutes=30 - i),
                               "price": 100 * 1.0005 ** i} for i in range(31)])
        row = signal("G1PQT3", symbol="SPY")
        enriched = enrich_confirmation(row, frame)
        self.assertTrue(enriched["frozen_trend_vote"])
        self.assertEqual(g.executable_votes("G1PQT3", enriched, 10.01, 9.99),
                         ("PT315T75", "QV4XU1S3", "TRENDX2"))
        gap = enrich_confirmation(row, frame.drop(index=12))
        self.assertFalse(gap["frozen_trend_vote"])
        old = {**enriched, "frozen_trend_timestamp": (NOW - timedelta(minutes=3)).isoformat()}
        self.assertNotIn("TRENDX2", g.executable_votes("G1PQT3", old, 10.01, 9.99))

    def test_minute_source_mutation_does_not_change_children(self):
        source = importlib.import_module("strategies.strategy_trendx2")
        prices = [100 * 1.0005 ** i for i in range(31)]
        def run():
            child = m.G1TN500Strategy()
            return [child.on_snapshot(snapshot(NOW + timedelta(minutes=i), price))
                    for i, price in enumerate(prices)]
        expected = run()
        with patch.dict(source.PARAMS, {"ret30": 999, "stop": 99}), patch.object(source, "UNIVERSE", ()):
            self.assertEqual(run(), expected)

    def test_minute_worker_shards_construct_frozen_classes(self):
        strategies = [getattr(m, sid + "Strategy")() for sid in sorted(m.IDS)]
        with patch.object(registry, "MINUTE_STRATEGIES", strategies):
            pool = registry.MinuteStrategyPool(shard_count=2, timeout_seconds=5)
            try:
                self.assertEqual({spec[0] for spec in pool.specs}, m.IDS)
                for i in range(31):
                    signals, errors = pool.evaluate(snapshot(NOW + timedelta(minutes=i), 100 * 1.0005 ** i))
                    self.assertEqual(errors, [])
                self.assertTrue(signals)
                self.assertTrue({row.strategy_id for row in signals} <= m.IDS)
            finally:
                pool.close()


class GenerationOneExecutionTests(unittest.TestCase):
    def tracker(self, temp):
        return GenerationOneBidAskTracker(temp, now_provider=lambda: NOW)

    def test_ask_entry_bid_exit_partial_fills_restart_and_no_legacy_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = self.tracker(temp)
            self.assertTrue(tracker.register_signal(signal(), quote(size=7), NOW))
            entry = tracker.active["one"]
            self.assertEqual(entry["filled_qty"], 7)
            self.assertEqual(entry["entry_price"], 10.01)
            self.assertEqual(entry["entry_fill_outcome"], "PARTIAL")
            later = NOW + timedelta(minutes=1)
            self.assertEqual(tracker.update_quotes({"XYZ": quote(later, bid=10.6, ask=10.62, size=3)}, later), [])
            self.assertEqual(tracker.active["one"]["remaining_qty"], 4)
            tracker = self.tracker(temp)
            self.assertEqual(tracker.active["one"]["remaining_qty"], 4)
            self.assertEqual(tracker.update_quotes({"XYZ": quote(later, bid=10.6, ask=10.62, size=3)}, later), [])
            last = later + timedelta(seconds=1)
            exits = tracker.update_quotes({"XYZ": quote(last, bid=10.5, ask=10.52, size=10)}, last)
            self.assertEqual(len(exits), 1)
            self.assertAlmostEqual(exits[0]["exit_price"], (3 * 10.6 + 4 * 10.5) / 7)
            self.assertAlmostEqual(exits[0]["pnl"], 3 * 10.6 + 4 * 10.5 - 7 * 10.01)
            self.assertFalse(self.tracker(temp).active)
            self.assertFalse((Path(temp) / "paper_signal_outcomes.jsonl").exists())
            self.assertFalse((Path(temp) / "paper_signal_v4_bidask_independent_outcomes.jsonl").exists())

    def test_shared_liquidity_consumed_once_per_experiment_not_per_constituent(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = self.tracker(temp)
            self.assertTrue(tracker.register_signal(signal("G1PQUW"), quote(size=25), NOW))
            self.assertEqual(tracker.active["one"]["requested_qty"], 199)
            self.assertEqual(tracker.active["one"]["filled_qty"], 25)
            self.assertFalse(tracker.register_signal(signal("G1PQUW", "two"), quote(size=25), NOW))
            # A separate experiment is a counterfactual, not another sleeve.
            self.assertTrue(tracker.register_signal(signal("G1PQG", "other"), quote(size=25), NOW))

    def test_missing_stale_delayed_and_zero_quotes_never_fill_later(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = self.tracker(temp)
            for setup, book in (("missing", None), ("stale", quote(NOW - timedelta(seconds=6))), ("zero", quote(size=0)), ("unknownsize", quote(ask_size_raw=None))):
                self.assertFalse(tracker.register_signal(signal(setup=setup), book, NOW))
            self.assertFalse(tracker.active)
            self.assertEqual(tracker.update_quotes({"XYZ": quote()}, NOW), [])
            self.assertFalse(tracker.register_signal(signal(setup="missing"), quote(), NOW))

    def test_stale_and_missing_bid_size_cannot_close_position(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = self.tracker(temp)
            tracker.register_signal(signal(), quote(size=10), NOW)
            later = NOW + timedelta(minutes=1)
            for book in (quote(NOW, bid=10.6, ask=10.62), quote(later, bid=10.6, ask=10.62, bid_size_raw=None), quote(later, bid=10.6, ask=10.62, size=0)):
                self.assertEqual(tracker.update_quotes({"XYZ": book}, later), [])
                self.assertEqual(tracker.active["one"]["remaining_qty"], 10)

    def test_quote_ask_not_last_controls_consensus_and_union_gates(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = self.tracker(temp)
            row = signal(target_price=10.5, original_target_price=10.12)
            self.assertFalse(tracker.register_signal(row, quote(ask=10.1), NOW))
            self.assertTrue(tracker.register_signal({**row, "strategy_id": "G1PQU", "setup_id": "union"}, quote(ask=10.1), NOW))
            self.assertEqual(tracker.active["union"]["constituent_votes"], ["PT315G1525"])

    def test_fixed_sizes_agreement_weights_cash_and_risk_caps(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = self.tracker(temp)
            for sid, expected in (("G1PGN500", 49), ("G1PGN1500", 149), ("G1PGN2500", 249), ("G1PGC5", 24), ("G1PGR10", 9), ("G1PGE25000", 490)):
                self.assertTrue(tracker.register_signal(signal(sid, sid), quote(), NOW))
                self.assertEqual(tracker.active[sid]["requested_qty"], expected, sid)
            self.assertTrue(tracker.register_signal(signal("G1PGN2500", "cash2", symbol="ABC"), quote(), NOW))
            self.assertTrue(tracker.register_signal(signal("G1PGN2500", "cash3", symbol="DEF"), quote(), NOW))
            self.assertLess(tracker.active["cash3"]["notional"], 30)
            self.assertFalse(tracker.register_signal(signal("G1PGN2500", "cash4", symbol="HIJ"), quote(), NOW))

    def test_birth_is_durable_replay_is_rejected_and_source_returns_never_copied(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = self.tracker(temp)
            births = copy.deepcopy(tracker.births)
            old = signal(timestamp=(NOW - timedelta(minutes=1)).isoformat())
            self.assertFalse(tracker.register_signal(old, quote(), NOW))
            later = GenerationOneBidAskTracker(temp, now_provider=lambda: NOW + timedelta(days=1))
            self.assertEqual(later.births, births)
            self.assertFalse(later.active)

    def test_corrupt_birth_provenance_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            self.tracker(temp)
            (Path(temp) / (FILE_STEM + "_births.json")).write_text("{")
            with self.assertRaises(ValueError):
                self.tracker(temp)

    def test_gain_checkpoint_uses_bid_mfe_and_sticky_partial_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = self.tracker(temp)
            tracker.register_signal(signal(), quote(size=10), NOW)
            later = NOW + timedelta(minutes=15)
            self.assertEqual(tracker.update_quotes({"XYZ": quote(later, bid=10, ask=10.02, size=3)}, later), [])
            self.assertEqual(tracker.active["one"]["pending_exit_reason"], "CONDITIONAL_REACH_900S")
            exits = tracker.update_quotes({"XYZ": quote(later + timedelta(seconds=1), bid=10.2, ask=10.22)}, later + timedelta(seconds=1))
            self.assertEqual(exits[0]["exit_reason"], "CONDITIONAL_REACH_900S")

    def test_reporting_actual_partial_quantities_and_zero_credit_before_birth(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = self.tracker(temp)
            before = calculate(temp, day="2026-09-30", as_of=NOW)
            self.assertFalse(set(before["modules"]) & {sid + "BA" for sid in IDS})
            tracker.register_signal(signal(), quote(size=7), NOW)
            later = NOW + timedelta(minutes=1)
            tracker.update_quotes({"XYZ": quote(later, bid=10.6, ask=10.62, size=3)}, later)
            with patch("reporting.all_engine_performance.load_market_marks", return_value={"equity": {"XYZ": {"bid": 10.4, "ask": 10.42}}}):
                report = calculate(temp, day="2026-10-01", as_of=later)
            module = report["modules"]["G1PQGBA"]
            self.assertAlmostEqual(module["pnl"], 3 * 10.6 + 4 * 10.4 - 7 * 10.01)
            self.assertEqual(module["taken"], 1)
            self.assertEqual(module["open_taken"], 1)
            self.assertFalse(module["portfolio_combinable"])
            self.assertEqual(len(report["modules"]), 51)
            self.assertEqual(report["diagnostics"]["generation_one"]["partial_exits"], 1)

    def test_reporting_never_resizes_and_honors_disabled_child(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = self.tracker(temp)
            tracker.register_signal(signal("G1PGE25000"), quote(size=200), NOW)
            later = NOW + timedelta(minutes=1)
            tracker.update_quotes({"XYZ": quote(later, bid=10.6, ask=10.62)}, later)
            report = calculate(temp, day="2026-10-01", as_of=later)
            module = report["modules"]["G1PGE25000BA"]
            self.assertAlmostEqual(module["pnl"], 200 * (10.6 - 10.01))
            self.assertAlmostEqual(module["return_pct"], module["pnl"] / 25000 * 100)
            switches = Path(temp) / "switches.json"
            switches.write_text(json.dumps({"G1PGE25000": False}))
            with patch.dict("os.environ", {"STRATEGY_OUTPUT_SWITCHES_PATH": str(switches)}):
                self.assertNotIn("G1PGE25000BA", calculate(temp, day="2026-10-01", as_of=later)["modules"])

    def test_liquidity_recovery_uses_ledger_even_without_any_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = self.tracker(temp)
            tracker.register_signal(signal("G1PGN500"), quote(size=10), NOW)
            tracker.state_path.unlink()
            tracker.liquidity_path.unlink()
            recovered = self.tracker(temp)
            self.assertEqual(recovered.active["one"]["remaining_qty"], 10)
            self.assertFalse(recovered.register_signal(signal("G1PGN500", "two"), quote(size=10), NOW))

    def test_old_book_or_size_fallback_does_not_replenish_liquidity(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = self.tracker(temp)
            book = quote(size=10, ask_size_raw=None, ask_size=10)
            self.assertTrue(tracker.register_signal(signal("G1PGN500"), book, NOW))
            self.assertFalse(tracker.register_signal(signal("G1PGN500", "two"), book, NOW))
            self.assertFalse(tracker.register_signal(signal("G1PGN500", "three"), quote(NOW - timedelta(seconds=1)), NOW))

    def test_partial_exits_share_bid_liquidity_between_positions(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = self.tracker(temp)
            tracker.register_signal(signal("G1PGN500", "one"), quote(size=5), NOW)
            next_time = NOW + timedelta(seconds=1)
            tracker.register_signal(signal("G1PGN500", "two", timestamp=next_time.isoformat()), quote(next_time, size=5), next_time)
            later = NOW + timedelta(minutes=1)
            exits = tracker.update_quotes({"XYZ": quote(later, bid=10.6, ask=10.62, size=7)}, later)
            self.assertEqual(len(exits), 1)
            self.assertEqual(sum(row["remaining_qty"] for row in tracker.active.values()), 3)
            self.assertEqual(tracker.update_quotes({"XYZ": quote(later, bid=10.6, ask=10.62, size=7)}, later), [])

    def test_portfolio_cash_is_preserved_across_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = self.tracker(temp)
            tracker.register_signal(signal("G1PGN2500", "one"), quote(), NOW)
            key, cash = tracker._cash_for("G1PGN2500", NOW)
            recovered = self.tracker(temp)
            self.assertEqual(recovered._cash_for("G1PGN2500", NOW), (key, cash))
            self.assertTrue(recovered.register_signal(signal("G1PGN2500", "two", symbol="ABC"), quote(), NOW))
            self.assertLess(recovered._cash_for("G1PGN2500", NOW)[1], 30)

    def test_unmarked_portfolio_is_omitted_instead_of_false_zero_return(self):
        with tempfile.TemporaryDirectory() as temp:
            tracker = self.tracker(temp)
            tracker.register_signal(signal(), quote(), NOW)
            report = calculate(temp, day="2026-10-01", as_of=NOW)
            self.assertNotIn("G1PQGBA", report["modules"])
            self.assertEqual(report["diagnostics"]["generation_one"]["unmarked"], 1)


if __name__ == "__main__":
    unittest.main()
