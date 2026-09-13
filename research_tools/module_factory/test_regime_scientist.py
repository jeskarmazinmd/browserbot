import random
import unittest

from research_tools.module_factory.regime_scientist import (
    discover_regimes,
    evaluate_regime,
)
from research_tools.module_factory.research_rows import (
    UnifiedResearchRow,
)


def make_row(
    i,
    *,
    x,
    regime,
    noise,
    outcome,
):
    return UnifiedResearchRow(
        symbol=f"S{i % 25:02d}",
        minute=i,
        price=100.0,
        features={
            "x": x,
            "regime": regime,
            "noise": noise,
        },
        forward_returns={
            10: outcome,
        },
        feature_ancestry={
            "x": ("PRICE",),
            "regime": (
                "LEVEL1_SNAPSHOT",
            ),
            "noise": ("DERIVED",),
        },
    )


class RegimeScientistTests(
    unittest.TestCase
):
    def reversal_rows(self):
        rng = random.Random(
            20260902
        )

        rows = []

        for i in range(1200):
            x = rng.gauss(
                0.0,
                1.0,
            )

            regime = rng.uniform(
                -1.0,
                1.0,
            )

            noise = rng.gauss(
                0.0,
                1.0,
            )

            if regime < 0.0:
                coefficient = 0.09
            else:
                coefficient = -0.09

            outcome = (
                coefficient * x
                + rng.gauss(
                    0.0,
                    0.025,
                )
            )

            rows.append(
                make_row(
                    i,
                    x=x,
                    regime=regime,
                    noise=noise,
                    outcome=outcome,
                )
            )

        return rows

    def one_sided_rows(self):
        rng = random.Random(99)

        rows = []

        for i in range(1200):
            x = rng.gauss(
                0.0,
                1.0,
            )

            regime = rng.uniform(
                -1.0,
                1.0,
            )

            noise = rng.gauss(
                0.0,
                1.0,
            )

            coefficient = (
                0.10
                if regime > 0.35
                else 0.0
            )

            outcome = (
                coefficient * x
                + rng.gauss(
                    0.0,
                    0.03,
                )
            )

            rows.append(
                make_row(
                    i,
                    x=x,
                    regime=regime,
                    noise=noise,
                    outcome=outcome,
                )
            )

        return rows

    def test_sign_reversal_is_detected(self):
        result = evaluate_regime(
            self.reversal_rows(),
            feature="x",
            regime_feature="regime",
            horizon=10,
            low_quantile=0.25,
            high_quantile=0.75,
            min_samples_per_regime=100,
        )

        self.assertIsNotNone(result)
        self.assertTrue(
            result.sign_reversal
        )

        self.assertGreater(
            result.low_correlation,
            0.8,
        )

        self.assertLess(
            result.high_correlation,
            -0.8,
        )

    def test_directions_are_empirical(self):
        result = evaluate_regime(
            self.reversal_rows(),
            feature="x",
            regime_feature="regime",
            horizon=10,
            min_samples_per_regime=100,
        )

        self.assertEqual(
            result.direction_low,
            1,
        )

        self.assertEqual(
            result.direction_high,
            -1,
        )

    def test_global_relationship_can_hide_reversal(self):
        result = evaluate_regime(
            self.reversal_rows(),
            feature="x",
            regime_feature="regime",
            horizon=10,
            min_samples_per_regime=100,
        )

        self.assertLess(
            abs(
                result.global_correlation
            ),
            0.15,
        )

        self.assertGreater(
            result.regime_difference,
            1.5,
        )

    def test_one_regime_can_dominate(self):
        result = evaluate_regime(
            self.one_sided_rows(),
            feature="x",
            regime_feature="regime",
            horizon=10,
            low_quantile=0.25,
            high_quantile=0.75,
            min_samples_per_regime=100,
        )

        self.assertGreater(
            abs(
                result.high_correlation
            ),
            abs(
                result.low_correlation
            ),
        )

        self.assertEqual(
            result.dominant_regime,
            "high",
        )

    def test_cross_family_ancestry_retained(self):
        result = evaluate_regime(
            self.reversal_rows(),
            feature="x",
            regime_feature="regime",
            horizon=10,
            min_samples_per_regime=100,
        )

        self.assertIn(
            "PRICE",
            result.ancestry,
        )

        self.assertIn(
            "LEVEL1_SNAPSHOT",
            result.ancestry,
        )

    def test_discovery_ranks_real_regime(self):
        discoveries = discover_regimes(
            self.reversal_rows(),
            feature_names=(
                "x",
                "noise",
            ),
            regime_feature_names=(
                "regime",
                "noise",
            ),
            horizons=(10,),
            quantile_pairs=(
                (0.25, 0.75),
            ),
            min_samples_per_regime=100,
            min_regime_difference=0.10,
            max_results=10,
        )

        self.assertTrue(discoveries)

        top = discoveries[0]

        self.assertEqual(
            top.feature,
            "x",
        )

        self.assertEqual(
            top.regime_feature,
            "regime",
        )

        self.assertTrue(
            top.sign_reversal
        )

    def test_invalid_quantiles_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            evaluate_regime(
                self.reversal_rows(),
                feature="x",
                regime_feature="regime",
                horizon=10,
                low_quantile=0.8,
                high_quantile=0.2,
            )

    def test_insufficient_samples_rejected(self):
        result = evaluate_regime(
            self.reversal_rows()[:20],
            feature="x",
            regime_feature="regime",
            horizon=10,
            min_samples_per_regime=30,
        )

        self.assertIsNone(result)

    def test_discovery_is_bounded(self):
        discoveries = discover_regimes(
            self.reversal_rows(),
            feature_names=(
                "x",
                "noise",
            ),
            regime_feature_names=(
                "regime",
                "noise",
            ),
            horizons=(10,),
            min_samples_per_regime=50,
            min_regime_difference=0.0,
            max_results=2,
        )

        self.assertLessEqual(
            len(discoveries),
            2,
        )

    def test_ids_are_deterministic(self):
        rows = self.reversal_rows()

        first = evaluate_regime(
            rows,
            feature="x",
            regime_feature="regime",
            horizon=10,
        )

        second = evaluate_regime(
            rows,
            feature="x",
            regime_feature="regime",
            horizon=10,
        )

        self.assertEqual(
            first.discovery_id,
            second.discovery_id,
        )


if __name__ == "__main__":
    unittest.main()
