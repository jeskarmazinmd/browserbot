from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from live_nh015_execution import (
    NH015LiveBook,
    STRATEGY_ID,
    cash_only_preflight_findings,
    configured_for_nh015,
    nh015_should_exit,
    partition_broker_preflight_findings,
    unfunded_order_probe_enabled,
)


class NH015LiveBookTests(unittest.TestCase):
    def setUp(self):
        self.old_env = dict(os.environ)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 9, 3, 15, 0, tzinfo=timezone.utc)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        self.temp.cleanup()

    def signal(self, number=1, entry=10.0, stop=9.9):
        return {
            "strategy_id": STRATEGY_ID,
            "setup_id": f"{STRATEGY_ID}|TEST{number}|{self.now.isoformat()}",
            "symbol": f"TEST{number}",
            "timestamp": self.now.isoformat(),
            "entry_price": entry,
            "stop_price": stop,
            "target_price": entry * 1.02,
        }

    def test_live_arm_requires_master_and_exact_strategy(self):
        os.environ["LIVE_ORDER_PLACEMENT_ENABLED"] = "1"
        self.assertFalse(configured_for_nh015())
        os.environ["LIVE_STRATEGY_ID"] = "C3N25S10"
        self.assertFalse(configured_for_nh015())
        os.environ["LIVE_STRATEGY_ID"] = STRATEGY_ID
        self.assertTrue(configured_for_nh015())

    def test_cash_failure_blocks_by_default(self):
        blockers, advisories = partition_broker_preflight_findings([
            "insufficient_broker_cash",
            "untracked_broker_position_exists",
            "broker_order_query_failed",
        ])
        self.assertEqual([
            "insufficient_broker_cash",
            "untracked_broker_position_exists",
            "broker_order_query_failed",
        ], blockers)
        self.assertEqual([], advisories)

    def test_cash_failure_is_advisory_only_in_explicit_unfunded_probe(self):
        os.environ["LIVE_UNFUNDED_ORDER_PROBE_ENABLED"] = "1"
        self.assertTrue(unfunded_order_probe_enabled())
        blockers, advisories = partition_broker_preflight_findings([
            "insufficient_broker_cash",
            "untracked_broker_position_exists",
        ])
        self.assertEqual(["untracked_broker_position_exists"], blockers)
        self.assertEqual(["insufficient_broker_cash"], advisories)

    def test_unfunded_probe_is_off_by_default(self):
        self.assertFalse(unfunded_order_probe_enabled())

    def test_margin_buying_power_never_substitutes_for_cash(self):
        findings = cash_only_preflight_findings({
            "cashBalance": 0.0,
            "availableFunds": 5000.0,
            "buyingPower": 20000.0,
            "dayTradingBuyingPower": 40000.0,
        }, 1000.0)
        self.assertEqual(["insufficient_broker_cash"], findings)

    def test_cash_check_uses_maximum_limit_cost(self):
        self.assertEqual(
            ["insufficient_broker_cash"],
            cash_only_preflight_findings({"cashBalance": 1000.0}, 1000.01),
        )
        self.assertEqual(
            [],
            cash_only_preflight_findings({"cashBalance": 1000.01}, 1000.01),
        )

    def test_missing_cash_field_fails_closed(self):
        self.assertEqual(
            ["broker_cash_balance_unavailable"],
            cash_only_preflight_findings({"buyingPower": 20000.0}, 1000.0),
        )

    def test_unfunded_advisory_precedes_real_order_transport(self):
        root = Path(__file__).parents[1]
        runner = (root / "live_strategy_runner.py").read_text()
        partition_at = runner.index(
            "partition_broker_preflight_findings(preflight_findings)"
        )
        attempt_at = runner.index(
            '"ENTRY_TRIGGER_OCO_ATTEMPT"', partition_at
        )
        transport_at = runner.index(
            "trader.place_entry_trigger_oco_order(", attempt_at
        )
        self.assertLess(partition_at, attempt_at)
        self.assertLess(attempt_at, transport_at)

    def test_production_image_and_runner_are_wired_fail_closed(self):
        root = Path(__file__).parents[1]
        dockerfile = (root / "Dockerfile").read_text()
        runner = (root / "live_strategy_runner.py").read_text()
        duplicate = (root / "strategies" / "c3_nh015_duplicate.py").read_text()
        self.assertIn("COPY live_nh015_execution.py .", dockerfile)
        self.assertIn("for e in live_nh015_candidates:", runner)
        self.assertNotIn("for e in events_a:\n", runner)
        self.assertIn("return configured_for_nh015()", runner)
        self.assertIn('"live_order_placement": False', duplicate)

    def test_sizing_exactly_matches_risk_sized_simulator(self):
        book = NH015LiveBook(self.root, self.now)
        allocation, errors = book.allocation(self.signal(), self.now)
        self.assertEqual([], errors)
        self.assertEqual(500, allocation.risk_shares)
        self.assertEqual(100, allocation.position_shares)
        self.assertEqual(500, allocation.cash_shares)
        self.assertEqual(100, allocation.shares)
        self.assertEqual(1000.0, allocation.reserved_cost)

    def test_five_slots_then_capital_reuse_and_equity_resizing(self):
        book = NH015LiveBook(self.root, self.now)
        for number in range(1, 6):
            signal = self.signal(number)
            allocation, errors = book.allocation(signal, self.now)
            self.assertEqual([], errors)
            self.assertEqual(100, allocation.shares)
            book.record_attempt(signal, allocation, self.now)
            book.record_submission(signal["setup_id"], str(number))
        sixth, errors = book.allocation(self.signal(6), self.now)
        self.assertIsNone(sixth)
        self.assertEqual(["insufficient_virtual_capital"], errors)

        first_setup = self.signal(1)["setup_id"]
        book.close(first_setup, 100.0, {"exit_reason": "TEST"})
        replacement, errors = book.allocation(self.signal(6), self.now)
        self.assertEqual([], errors)
        self.assertEqual(102, replacement.shares)
        self.assertAlmostEqual(5100.0, replacement.equity)

    def test_state_is_durable_and_duplicate_setup_is_rejected(self):
        book = NH015LiveBook(self.root, self.now)
        signal = self.signal()
        allocation, _ = book.allocation(signal, self.now)
        book.record_attempt(signal, allocation, self.now)
        loaded = NH015LiveBook(self.root, self.now)
        self.assertIn(signal["setup_id"], loaded.state["attempted"])
        duplicate, errors = loaded.allocation(signal, self.now)
        self.assertIsNone(duplicate)
        self.assertIn("setup_already_attempted", errors)

    def test_new_day_resets_only_when_flat(self):
        book = NH015LiveBook(self.root, self.now)
        tomorrow = self.now + timedelta(days=1)
        self.assertTrue(book.rollover(tomorrow))
        self.assertEqual("2026-09-04", book.state["market_day"])
        history = json.loads(book.history_path.read_text())
        self.assertEqual(5000.0, history["2026-09-03"]["end_equity"])

        signal = self.signal(2)
        signal["timestamp"] = tomorrow.isoformat()
        signal["setup_id"] = f"{STRATEGY_ID}|TEST2|{tomorrow.isoformat()}"
        allocation, _ = book.allocation(signal, tomorrow)
        book.record_attempt(signal, allocation, tomorrow)
        book.record_submission(signal["setup_id"], "2")
        self.assertFalse(book.rollover(tomorrow + timedelta(days=1)))

    def test_no_new_high_exit_activates_and_resets_on_new_high(self):
        activated = self.now
        position = {
            "actual_entry_price": 100.0,
            "entry_fill_time": activated.isoformat(),
            "highest_price_since_fill": 100.0,
            "mfe_at": activated.isoformat(),
        }
        self.assertFalse(nh015_should_exit(position, 100.30, activated))
        self.assertTrue(position["nh015_activated"])
        self.assertFalse(
            nh015_should_exit(position, 100.29, activated + timedelta(seconds=14))
        )
        self.assertFalse(
            nh015_should_exit(position, 100.40, activated + timedelta(seconds=15))
        )
        self.assertFalse(
            nh015_should_exit(position, 100.39, activated + timedelta(seconds=29))
        )
        self.assertTrue(
            nh015_should_exit(position, 100.39, activated + timedelta(seconds=30))
        )

if __name__ == "__main__":
    unittest.main()
