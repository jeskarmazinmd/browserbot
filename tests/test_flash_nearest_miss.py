import unittest

from strategies.flash_nearest_miss import score


class FlashNearestMissTests(unittest.TestCase):
    def setUp(self):
        self.measurement = {
            "symbol": "TEST", "price": 99.2, "flash_drop_pct": 0.8,
            "pre_return_pct": 0.30, "pre_slope_pct_per_hour": 0.60,
            "pre_r2": 0.50,
        }

    def test_a_and_d_are_scored_independently(self):
        a = score(self.measurement, "A", {"flash_drop_pct": 1.0}, .25, .5, 12)
        d = score(self.measurement, "D", {"flash_drop_pct": .9}, .25, .5, 12)
        self.assertEqual(a["failed_rules"][0]["rule"], "flash_drop_pct")
        self.assertAlmostEqual(a["failed_rules"][0]["shortfall"], .2)
        self.assertAlmostEqual(d["failed_rules"][0]["shortfall"], .1)

    def test_h_additional_rules_are_exact(self):
        row = dict(self.measurement, pre_r2=.35, pre_slope_pct_per_hour=13)
        h = score(row, "H", {
            "flash_drop_pct": .6, "max_flash_drop_pct": 2.5,
            "min_pre_r2": .4, "max_pre_slope_pct_per_hour": 12,
        }, .25, .5, 12)
        names = [rule["rule"] for rule in h["failed_rules"]]
        self.assertIn("pre_r2", names)
        self.assertIn("pre_slope_pct_per_hour", names)

    def test_full_qualifier_is_not_a_near_miss(self):
        row = dict(self.measurement, flash_drop_pct=1.1)
        self.assertIsNone(score(row, "A", {"flash_drop_pct": 1.0}, .25, .5, 12))


if __name__ == "__main__":
    unittest.main()
