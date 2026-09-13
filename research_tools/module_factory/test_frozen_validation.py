import unittest

from research_tools.module_factory.frozen_validation import (
    validate_fixed_anomaly_large_move,
    validate_fixed_distribution_mean,
    validate_fixed_lag,
    validate_fixed_regime,
)
from research_tools.module_factory.research_rows import (
    UnifiedResearchRow,
)


def row(
    symbol,
    minute,
    *,
    features,
    outcome,
):
    return UnifiedResearchRow(
        symbol=symbol,
        minute=minute,
        price=100.0,
        features=features,
        forward_returns={
            10: outcome,
            20: outcome,
        },
    )


class FrozenValidationTests(unittest.TestCase):

    def test_regime_uses_fixed_boundaries_and_signs(self):
        rows = [
            row(
                "A", 1,
                features={"r": -2, "k": 0.1},
                outcome=-2,
            ),
            row(
                "A", 2,
                features={"r": 0, "k": 0.1},
                outcome=0,
            ),
            row(
                "A", 3,
                features={"r": 2, "k": 0.1},
                outcome=2,
            ),
            row(
                "B", 1,
                features={"r": -2, "k": 5},
                outcome=2,
            ),
            row(
                "B", 2,
                features={"r": 0, "k": 5},
                outcome=0,
            ),
            row(
                "B", 3,
                features={"r": 2, "k": 5},
                outcome=-2,
            ),
        ]

        result = validate_fixed_regime(
            rows,
            feature="r",
            regime_feature="k",
            horizon=20,
            low_threshold=0.2,
            high_threshold=2.5,
            direction_low=1,
            direction_high=-1,
        )

        self.assertAlmostEqual(
            result.metrics["low_correlation"],
            1.0,
        )
        self.assertAlmostEqual(
            result.metrics["high_correlation"],
            -1.0,
        )
        self.assertAlmostEqual(
            result.primary_effect,
            1.0,
        )

    def test_lag_is_not_reselected(self):
        rows = [
            row(
                "A",
                minute,
                features={"r": float(minute)},
                outcome=float(minute - 3),
            )
            for minute in range(8)
        ]

        result = validate_fixed_lag(
            rows,
            feature="r",
            horizon=20,
            lag=3,
            direction=1,
        )

        self.assertEqual(
            result.metrics["lag"],
            3,
        )
        self.assertGreater(
            result.primary_effect,
            0,
        )

    def test_distribution_uses_fixed_thresholds(self):
        rows = [
            row(
                "A", 1,
                features={"a": -2},
                outcome=-0.5,
            ),
            row(
                "B", 1,
                features={"a": -3},
                outcome=-0.2,
            ),
            row(
                "C", 1,
                features={"a": 2},
                outcome=-0.3,
            ),
            row(
                "D", 1,
                features={"a": 3},
                outcome=-0.4,
            ),
            row(
                "E", 1,
                features={"a": 0},
                outcome=100,
            ),
        ]

        result = validate_fixed_distribution_mean(
            rows,
            feature="a",
            horizon=10,
            low_threshold=-1,
            high_threshold=1,
            direction_low=-1,
            direction_high=-1,
        )

        self.assertGreater(
            result.primary_effect,
            0,
        )
        self.assertEqual(
            result.n_samples,
            4,
        )

    def test_anomaly_tests_large_move_not_signed_mean(self):
        rows = []

        # Dense normal cloud.
        for i in range(20):
            rows.append(
                row(
                    f"N{i}",
                    i,
                    features={
                        "x": (i % 3) * 0.05,
                        "y": (i % 4) * 0.05,
                    },
                    outcome=0.1,
                )
            )

        # Extreme feature-space points with large returns.
        rows.extend([
            row(
                "A",
                30,
                features={"x": 10, "y": 10},
                outcome=-1.0,
            ),
            row(
                "B",
                31,
                features={"x": -10, "y": -10},
                outcome=-1.2,
            ),
        ])

        result = validate_fixed_anomaly_large_move(
            rows,
            features=("x", "y"),
            horizon=20,
            anomaly_threshold=3.0,
            move_threshold=0.5,
            expected_direction=-1,
        )

        self.assertGreater(
            result.primary_effect,
            0,
        )
        self.assertGreater(
            result.metrics["directional_difference"],
            0,
        )
        self.assertEqual(
            result.metrics["normalization"],
            "validation-sample-nuisance",
        )


if __name__ == "__main__":
    unittest.main()
