import unittest
from datetime import datetime, timedelta, timezone

from research_tools.module_factory.cross_sectional_scientist import (
    analyze_minute,
    discover,
    discover_feature,
)
from research_tools.module_factory.feature_matrix import FeatureRow


class CrossSectionalScientistTests(unittest.TestCase):
    def _rows(
        self,
        *,
        inverse=False,
    ):
        rows = []

        base = datetime(
            2026, 1, 2, 14, 30,
            tzinfo=timezone.utc,
        )

        for minute_index in range(30):
            minute = (
                base
                + timedelta(
                    minutes=minute_index
                )
            )

            for symbol_index in range(50):
                x = (
                    symbol_index - 25
                ) / 25.0

                y = (
                    -x
                    if inverse
                    else x
                )

                rows.append(
                    FeatureRow(
                        symbol=(
                            f"S{symbol_index:03d}"
                        ),
                        minute=minute,
                        price=100.0,
                        features={
                            "signal": x,
                            "noise": (
                                (
                                    symbol_index * 17
                                    + minute_index * 11
                                )
                                % 101
                                - 50
                            ) / 50.0,
                        },
                        forward_returns={
                            10: y * 0.5,
                            20: y,
                        },
                    )
                )

        return rows

    def test_minute_detects_positive_ranking(self):
        rows = self._rows()[:50]

        evidence = analyze_minute(
            rows,
            feature="signal",
            horizon=20,
        )

        self.assertIsNotNone(evidence)

        self.assertGreater(
            evidence.rank_correlation,
            0.99,
        )

        self.assertGreater(
            evidence.high_minus_low,
            0.0,
        )

    def test_discovers_positive_cross_section(self):
        result = discover_feature(
            self._rows(),
            feature="signal",
            horizon=20,
        )

        self.assertIsNotNone(result)

        self.assertGreater(
            result.mean_rank_correlation,
            0.99,
        )

        self.assertEqual(
            result.preferred_sign,
            1,
        )

        self.assertGreater(
            result.positive_spread_fraction,
            0.99,
        )

    def test_discovers_inverse_cross_section(self):
        result = discover_feature(
            self._rows(inverse=True),
            feature="signal",
            horizon=20,
        )

        self.assertIsNotNone(result)

        self.assertLess(
            result.mean_rank_correlation,
            -0.99,
        )

        self.assertEqual(
            result.preferred_sign,
            -1,
        )

    def test_noise_ranks_below_planted_signal(self):
        results = discover(
            self._rows(),
            features=[
                "signal",
                "noise",
            ],
            horizons=(20,),
        )

        self.assertEqual(
            results[0].feature,
            "signal",
        )

    def test_requires_enough_symbols(self):
        result = discover_feature(
            self._rows(),
            feature="signal",
            horizon=20,
            min_cross_section=100,
        )

        self.assertIsNone(result)

    def test_multiple_horizons(self):
        results = discover(
            self._rows(),
            features=["signal"],
            horizons=(10, 20),
        )

        self.assertEqual(
            {result.horizon for result in results},
            {10, 20},
        )


if __name__ == "__main__":
    unittest.main()
