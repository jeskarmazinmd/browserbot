from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from nh015_execution_family import NH015ExecutionFamily, POLICIES, SOURCE_STRATEGY_ID


class NH015ExecutionFamilyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 9, 8, 15, 0, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def signal(self):
        return {
            "strategy_id": SOURCE_STRATEGY_ID,
            "setup_id": f"{SOURCE_STRATEGY_ID}|XYZ|{self.now.isoformat()}",
            "symbol": "XYZ",
            "timestamp": self.now.isoformat(),
            "entry_price": 100.0,
            "target_price": 101.0,
            "stop_price": 99.0,
        }

    def quote(self, bid=99.96, ask=100.0, *, at=None, ask_size=1000):
        at = at or self.now
        timestamp_ms = int(at.timestamp() * 1000)
        midpoint = (bid + ask) / 2.0
        spread_pct = ((ask - bid) / midpoint) * 100.0

        return {
            "bid": bid,
            "ask": ask,
            "bid_time_ms": timestamp_ms,
            "ask_time_ms": timestamp_ms,
            "realtime": True,
            "bid_size_raw": 1000,
            "ask_size_raw": ask_size,
            "spread_pct": spread_pct,
        }

    def test_fixed_family_registers_every_policy_once(self):
        tracker = NH015ExecutionFamily(self.root)
        rows = tracker.register(self.signal(), self.quote(), self.now)
        self.assertEqual(len(POLICIES), len(rows))
        self.assertEqual(6, len(tracker.active))
        self.assertEqual(3, len(tracker.pending))
        self.assertEqual([], tracker.register(self.signal(), self.quote(), self.now))

    def test_ioc_buffers_pay_observed_ask_not_limit(self):
        tracker = NH015ExecutionFamily(self.root)
        tracker.register(self.signal(), self.quote(100.0, 100.05), self.now)
        by_strategy = {row["strategy_id"]: row for row in tracker.active.values()}
        self.assertEqual(100.05, by_strategy["C3N25S10NH015XBUF05"]["entry_price"])
        self.assertEqual(100.05, by_strategy["C3N25S10NH015XBUF05"]["limit_price"])
        self.assertEqual(100.05, by_strategy["C3N25S10NH015XBUF10"]["entry_price"])
        self.assertEqual(100.10, by_strategy["C3N25S10NH015XBUF10"]["limit_price"])

    def test_spread_and_edge_gates_fail_closed(self):
        tracker = NH015ExecutionFamily(self.root)
        rows = tracker.register(self.signal(), self.quote(99.0, 100.0), self.now)
        reasons = {r["strategy_id"]: r.get("reason") for r in rows}
        self.assertEqual("SPREAD_ABOVE_CAP", reasons["C3N25S10NH015XSP05"])
        self.assertEqual("SPREAD_ABOVE_CAP", reasons["C3N25S10NH015XSP10"])
        self.assertEqual(
            "EDGE_SPREAD_RATIO_BELOW_MINIMUM",
            reasons["C3N25S10NH015XEDGE3"],
        )

    def test_passive_touch_and_trade_through_are_distinct(self):
        tracker = NH015ExecutionFamily(self.root)
        tracker.register(self.signal(), self.quote(), self.now)
        # Midpoint is 99.98. Touch fills MID but not MIDTHRU; BID remains pending.
        at_5s = self.now + timedelta(seconds=5)
        tracker.update(
            {"XYZ": self.quote(99.96, 99.98, at=at_5s)},
            at_5s,
        )
        active_ids = {r["strategy_id"] for r in tracker.active.values()}
        pending_ids = {r["strategy_id"] for r in tracker.pending.values()}
        self.assertIn("C3N25S10NH015XMID", active_ids)
        self.assertIn("C3N25S10NH015XMIDTHRU", pending_ids)
        self.assertIn("C3N25S10NH015XBIDTHRU", pending_ids)

        at_10s = self.now + timedelta(seconds=10)
        tracker.update(
            {"XYZ": self.quote(99.90, 99.95, at=at_10s)},
            at_10s,
        )
        active_ids = {r["strategy_id"] for r in tracker.active.values()}
        self.assertIn("C3N25S10NH015XMIDTHRU", active_ids)
        self.assertIn("C3N25S10NH015XBIDTHRU", active_ids)

    def test_unfilled_passive_orders_expire(self):
        tracker = NH015ExecutionFamily(self.root)
        tracker.register(self.signal(), self.quote(), self.now)
        at_30s = self.now + timedelta(seconds=30)
        rows = tracker.update(
            {"XYZ": self.quote(100.1, 100.2, at=at_30s)},
            at_30s,
        )
        expired = [row for row in rows if row["event_type"] == "FAMILY_EXPIRE"]
        self.assertEqual(3, len(expired))
        self.assertEqual({}, tracker.pending)

    def test_longer_policy_uses_sixty_second_timer(self):
        tracker = NH015ExecutionFamily(self.root)
        tracker.register(self.signal(), self.quote(), self.now)
        at_5s = self.now + timedelta(seconds=5)
        tracker.update(
            {"XYZ": self.quote(100.31, 100.32, at=at_5s)},
            at_5s,
        )

        at_20s = self.now + timedelta(seconds=20)
        rows = tracker.update(
            {"XYZ": self.quote(100.31, 100.32, at=at_20s)},
            at_20s,
        )
        exits = {r["strategy_id"] for r in rows if r["event_type"] == "FAMILY_EXIT"}
        self.assertNotIn("C3N25S10NH015XLONG60", exits)

        at_65s = self.now + timedelta(seconds=65)
        rows = tracker.update(
            {"XYZ": self.quote(100.31, 100.32, at=at_65s)},
            at_65s,
        )
        exits = {r["strategy_id"] for r in rows if r["event_type"] == "FAMILY_EXIT"}
        self.assertIn("C3N25S10NH015XLONG60", exits)

    def test_restart_restores_pending_and_active_without_resurrection(self):
        tracker = NH015ExecutionFamily(self.root)
        tracker.register(self.signal(), self.quote(), self.now)
        restarted = NH015ExecutionFamily(self.root)
        self.assertEqual(6, len(restarted.active))
        self.assertEqual(3, len(restarted.pending))
        at_1s = self.now + timedelta(seconds=1)
        restarted.update(
            {"XYZ": self.quote(101.0, 101.01, at=at_1s)},
            at_1s,
        )
        stale = restarted.state_path.read_text()
        final = NH015ExecutionFamily(self.root)
        self.assertEqual(0, len(final.active))
        final.state_path.write_text(stale)
        final_again = NH015ExecutionFamily(self.root)
        self.assertEqual(0, len(final_again.active))

    def test_status_and_source_are_explicitly_paper_only(self):
        tracker = NH015ExecutionFamily(self.root)
        status = json.loads(tracker.status_path.read_text())
        self.assertTrue(status["paper_only"])
        self.assertFalse(status["broker_execution_enabled"])
        source = Path(__file__).parents[1].joinpath("nh015_execution_family.py").read_text()
        self.assertNotIn("SchwabTradeClient", source)
        self.assertNotIn("place_order", source)
        self.assertNotIn("requests.", source)

    def test_production_runner_and_image_are_wired(self):
        project = Path(__file__).parents[1]
        runner = project.joinpath("live_strategy_runner.py").read_text()
        dockerfile = project.joinpath("Dockerfile").read_text()
        self.assertIn("from nh015_execution_family import NH015ExecutionFamily", runner)
        self.assertIn("| nh015_execution_family.symbols()", runner)
        self.assertIn("nh015_execution_family.register(", runner)
        self.assertIn("nh015_execution_family.update(", runner)
        self.assertIn("COPY nh015_execution_family.py .", dockerfile)


if __name__ == "__main__":
    unittest.main()
