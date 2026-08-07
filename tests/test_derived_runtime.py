import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from paper_outcome_tracker import PaperOutcomeTracker
from strategies.derived_runtime import derive_signals


def parent(strategy_id):
    return {
        "strategy_id": strategy_id,
        "symbol": "XYZ",
        "timestamp": "2026-08-03T14:00:00+00:00",
        "setup_id": f"{strategy_id}|XYZ|2026-08-03T14:00:00+00:00",
        "entry_price": 100.0,
        "target_price": 106.0,
        "stop_price": 98.0 if strategy_id == "B" else 95.0,
        "volume_data_status_flash": "OK",
        "flash_dollar_volume_3m": 2_000_000,
        "flash_volume_ratio": 1.0,
        "confirmation_wait_seconds": 20.0,
        "rebound_volume_ratio": 0.5,
        "distance_below_rolling_vwap_pct": 0.75,
        "pre_return_pct": 1.0,
        "pre_r2": 0.7,
        "pre30_return_std_pct": 0.25,
        "flash_drop_pct": 1.0,
        "market_5m_return_pct": 0.1,
        "market_1m_return_pct": 0.05,
    }


class DerivedRuntimeTests(unittest.TestCase):
    def test_parent_routes(self):
        a_ids = {s["strategy_id"] for s in derive_signals(parent("A"))}
        self.assertTrue({"E", "I", "K1", "K9", "L", "M", "N", "O", "P", "Q", "R", "S"} <= a_ids)
        self.assertEqual({s["strategy_id"] for s in derive_signals(parent("D"))}, {"F"})
        self.assertEqual(
            {s["strategy_id"] for s in derive_signals(parent("B"))},
            {"C1", "C2", "C3", "C4", "G", "J1", "J2", "J3", "J4", "J5", "J6"},
        )

    def test_overlays_reject_missing_metrics(self):
        a = parent("A")
        a["volume_data_status_flash"] = "ERROR"
        a["confirmation_wait_seconds"] = None
        ids = {signal["strategy_id"] for signal in derive_signals(a)}
        self.assertNotIn("E", ids)
        self.assertNotIn("I", ids)

    def test_j_checkpoint_exit(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = PaperOutcomeTracker(root)
            j3 = next(s for s in derive_signals(parent("B")) if s["strategy_id"] == "J3")
            tracker.register(j3)
            rows = tracker.update({"XYZ": 99.9}, datetime(2026, 8, 3, 14, 0, 16, tzinfo=timezone.utc))
            self.assertEqual(rows[0]["exit_reason"], "NO_PROGRESS_CHECKPOINT")

    def test_c1_activates_then_trails(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = PaperOutcomeTracker(root)
            c1 = next(s for s in derive_signals(parent("B")) if s["strategy_id"] == "C1")
            tracker.register(c1)
            start = datetime(2026, 8, 3, 14, tzinfo=timezone.utc)
            self.assertEqual(tracker.update({"XYZ": 100.4}, start + timedelta(seconds=5)), [])
            rows = tracker.update({"XYZ": 100.1}, start + timedelta(seconds=10))
            self.assertEqual(rows[0]["exit_reason"], "TRAIL_PULLBACK")

    def test_g_uses_one_and_half_percent_stop(self):
        g = next(s for s in derive_signals(parent("B")) if s["strategy_id"] == "G")
        self.assertAlmostEqual(g["stop_price"], 98.5)

    def test_dynamic_state_survives_restart_checkpoint(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = PaperOutcomeTracker(root)
            c1 = next(s for s in derive_signals(parent("B")) if s["strategy_id"] == "C1")
            tracker.register(c1)
            start = datetime(2026, 8, 3, 14, tzinfo=timezone.utc)
            tracker.update({"XYZ": 100.4}, start + timedelta(seconds=5))
            tracker.checkpoint(force=True)
            restarted = PaperOutcomeTracker(root)
            rows = restarted.update({"XYZ": 100.1}, start + timedelta(seconds=10))
            self.assertEqual(rows[0]["exit_reason"], "TRAIL_PULLBACK")

    def test_k_fixed_and_conditional_rules(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = PaperOutcomeTracker(root)
            derived = {s["strategy_id"]: s for s in derive_signals(parent("A"))}
            tracker.register(derived["K1"])
            tracker.register(derived["K4"])
            now = datetime(2026, 8, 3, 14, 0, 31, tzinfo=timezone.utc)
            rows = tracker.update({"XYZ": 100.1}, now)
            self.assertEqual({row["strategy_id"] for row in rows}, {"K1"})
            self.assertIn("K4", {row["strategy_id"] for row in tracker.active.values()})

    def test_k_passed_checkpoint_survives_restart(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = PaperOutcomeTracker(root)
            k4 = next(s for s in derive_signals(parent("A")) if s["strategy_id"] == "K4")
            tracker.register(k4)
            tracker.update({"XYZ": 100.1}, datetime(2026, 8, 3, 14, 0, 31, tzinfo=timezone.utc))
            tracker.checkpoint(force=True)
            restarted = PaperOutcomeTracker(root)
            rows = restarted.update({"XYZ": 99.9}, datetime(2026, 8, 3, 14, 0, 40, tzinfo=timezone.utc))
            self.assertEqual(rows, [])

    def test_n_adaptive_trail(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = PaperOutcomeTracker(root)
            n = next(s for s in derive_signals(parent("A")) if s["strategy_id"] == "N")
            tracker.register(n)
            start = datetime(2026, 8, 3, 14, tzinfo=timezone.utc)
            tracker.update({"XYZ": 100.4}, start + timedelta(seconds=5))
            rows = tracker.update({"XYZ": 100.1}, start + timedelta(seconds=10))
            self.assertEqual(rows[0]["exit_reason"], "ADAPTIVE_TRAIL")

    def test_o_waits_for_second_leg(self):
        with tempfile.TemporaryDirectory() as root:
            tracker = PaperOutcomeTracker(root)
            o = next(s for s in derive_signals(parent("A")) if s["strategy_id"] == "O")
            tracker.register(o)
            initial = next(iter(tracker.active.values()))
            self.assertIsNone(initial.get("entry_timestamp"))
            start = datetime(2026, 8, 3, 14, tzinfo=timezone.utc)
            tracker.update({"XYZ": 100.3}, start + timedelta(seconds=5))
            tracker.update({"XYZ": 100.1}, start + timedelta(seconds=10))
            tracker.update({"XYZ": 100.21}, start + timedelta(seconds=15))
            record = next(iter(tracker.active.values()))
            self.assertTrue(record["entered"])
            self.assertAlmostEqual(record["entry_price"], 100.21)
            self.assertEqual(
                record["entry_timestamp"],
                (start + timedelta(seconds=15)).isoformat(),
            )

    def test_ls_filters_reject_failed_thresholds(self):
        cases = {
            "L": ("rebound_volume_ratio", 0.9),
            "M": ("distance_below_rolling_vwap_pct", 0.4),
            "P": ("pre_r2", 0.4),
            "Q": ("pre30_return_std_pct", 1.0),
            "S": ("market_1m_return_pct", -0.1),
        }
        for strategy_id, (field, value) in cases.items():
            candidate = parent("A")
            candidate[field] = value
            ids = {signal["strategy_id"] for signal in derive_signals(candidate)}
            self.assertNotIn(strategy_id, ids)

    def test_r_rejects_after_eleven_et(self):
        candidate = parent("A")
        candidate["timestamp"] = "2026-08-03T16:00:00+00:00"
        ids = {signal["strategy_id"] for signal in derive_signals(candidate)}
        self.assertNotIn("R", ids)


if __name__ == "__main__":
    unittest.main()
