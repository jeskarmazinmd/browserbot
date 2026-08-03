import unittest
from pathlib import Path
from types import SimpleNamespace

from strategies.nearest_miss import between, boolean, consider, maximum, minimum, reset


ACTIVE_MODULE_FILES = (
    "ema1", "ema2", "ema3", "sma1", "vwema1", "tf1",
    "rs1", "rs2", "rs3", "ve1", "vr1", "m1", "m2", "m3",
    "mc1", "tl1", "av1", "td1", "sh1", "cv1", "hl1", "vt1",
    "pd1", "bo1", "ge1", "gm1", "gp1", "gr1", "gt1", "or1",
)


class NearestMissTests(unittest.TestCase):
    def test_closest_rejected_candidate_wins(self):
        strategy = SimpleNamespace()
        reset(strategy)
        consider(strategy, "FAR", "now", 10, [minimum("rebound", 0.10, 0.25, "%")])
        consider(strategy, "CLOSE", "now", 10, [minimum("rebound", 0.24, 0.25, "%")])
        self.assertEqual(strategy.nearest_miss["symbol"], "CLOSE")
        self.assertAlmostEqual(strategy.nearest_miss["failed_rules"][0]["shortfall"], 0.01)

    def test_passing_candidate_is_not_a_near_miss(self):
        strategy = SimpleNamespace()
        reset(strategy)
        retained = consider(strategy, "PASS", "now", 10, [
            minimum("min", 2, 1), maximum("max", 1, 2),
            between("range", 2, 1, 3), boolean("flag", True),
        ])
        self.assertFalse(retained)
        self.assertIsNone(strategy.nearest_miss)

    def test_every_active_minute_module_is_instrumented(self):
        root = Path(__file__).resolve().parents[1] / "strategies"
        missing = []
        for module in ACTIVE_MODULE_FILES:
            source = (root / f"strategy_{module}.py").read_text()
            if "nearest_miss import" not in source or "consider(" not in source or "reset(self)" not in source:
                missing.append(module)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
