import unittest
from datetime import datetime, timedelta, timezone

from research_tools.module_factory.discovery_engine import (
    _bh_passes,
    _ranks,
    discover,
)
from research_tools.module_factory.feature_matrix import FeatureRow


class DiscoveryEngineTests(unittest.TestCase):
    def _rows(self, day: int, reverse: bool = False):
        base = datetime(
            2026, 1, day, 14, 30, tzinfo=timezone.utc
        )

        rows = []

        for i in range(200):
            x = float(i)

            # Strong deterministic relationship.
            y = (x - 100.0) / 100.0

            if reverse:
                y = -y

            rows.append(
                FeatureRow(
                    symbol=f"S{i % 20:02d}",
                    minute=base + timedelta(minutes=i),
                    price=100.0,
                    features={
                        "signal": x,
                        "noise": float((i * 37) % 101),
                    },
                    forward_returns={
                        1: y,
                        5: y,
                        10: y,
                        20: y,
                    },
                )
            )

        return rows

    def test_average_ranks_for_ties(self):
        self.assertEqual(
            _ranks([10.0, 20.0, 20.0, 30.0]),
            [1.0, 2.5, 2.5, 4.0],
        )

    def test_finds_repeatable_relationship(self):
        results = discover(
            {
                "2026-01-02": self._rows(2),
                "2026-01-03": self._rows(3),
            },
            horizons=(20,),
            min_observations_per_day=100,
        )

        signal = next(
            x for x in results
            if x.feature == "signal"
        )

        self.assertGreater(signal.mean_spearman, 0.99)
        self.assertGreater(signal.worst_day_edge, 0)
        self.assertEqual(signal.sign_consistency, 1.0)
        self.assertTrue(signal.bh_pass)

    def test_inconsistent_days_are_penalized(self):
        results = discover(
            {
                "2026-01-02": self._rows(2),
                "2026-01-03": self._rows(3, reverse=True),
            },
            horizons=(20,),
            min_observations_per_day=100,
        )

        signal = next(
            x for x in results
            if x.feature == "signal"
        )

        self.assertLessEqual(signal.sign_consistency, 0.5)
        self.assertLessEqual(signal.worst_day_edge, 0)

    def test_all_horizons_can_be_examined(self):
        results = discover(
            {
                "2026-01-02": self._rows(2),
                "2026-01-03": self._rows(3),
            },
            min_observations_per_day=100,
        )

        horizons = {
            x.horizon
            for x in results
            if x.feature == "signal"
        }

        self.assertEqual(horizons, {1, 5, 10, 20})


if __name__ == "__main__":
    unittest.main()
