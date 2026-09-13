import random
import unittest

from research_tools.module_factory.anomaly_scientist import (
    discover_anomaly_states,
    evaluate_anomaly_state,
)
from research_tools.module_factory.research_rows import (
    UnifiedResearchRow,
)


def make_rows(
    seed=20260902,
):
    rng = random.Random(seed)

    rows = []

    for i in range(3000):
        a = rng.gauss(
            0.0,
            1.0,
        )

        b = rng.gauss(
            0.0,
            1.0,
        )

        noise = rng.gauss(
            0.0,
            1.0,
        )

        outcome = rng.gauss(
            0.0,
            0.01,
        )

        # Jointly unusual multivariate state.
        #
        # The planted event is radial: neither a nor b alone
        # defines it. This matches the scientist's squared-distance
        # anomaly definition while preserving feature-only detection.
        joint_distance = (
            a * a
            + b * b
        )

        if joint_distance > 5.0:
            magnitude = (
                0.12
                + abs(
                    rng.gauss(
                        0.0,
                        0.02,
                    )
                )
            )

            outcome = (
                magnitude
                if rng.random() < 0.5
                else -magnitude
            )

        rows.append(
            UnifiedResearchRow(
                symbol=f"S{i % 40:02d}",
                minute=i,
                price=100.0,
                features={
                    "a": a,
                    "b": b,
                    "noise": noise,
                },
                forward_returns={
                    10: outcome,
                },
                feature_ancestry={
                    "a": ("PRICE",),
                    "b": (
                        "LEVEL1_SNAPSHOT",
                    ),
                    "noise": (
                        "DERIVED",
                    ),
                },
            )
        )

    return rows


def make_directional_rows(
    seed=91,
):
    rng = random.Random(seed)

    rows = []

    for i in range(2500):
        a = rng.gauss(
            0.0,
            1.0,
        )

        b = rng.gauss(
            0.0,
            1.0,
        )

        distance = (
            a * a
            + b * b
        )

        outcome = rng.gauss(
            0.0,
            0.02,
        )

        if distance > 6.0:
            outcome = (
                0.08
                + rng.gauss(
                    0.0,
                    0.015,
                )
            )

        rows.append(
            UnifiedResearchRow(
                symbol=f"S{i % 30:02d}",
                minute=i,
                price=100.0,
                features={
                    "a": a,
                    "b": b,
                },
                forward_returns={
                    10: outcome,
                },
                feature_ancestry={
                    "a": ("PRICE",),
                    "b": ("TEMPORAL",),
                },
            )
        )

    return rows


class AnomalyScientistTests(
    unittest.TestCase
):
    def test_multivariate_anomaly_changes_move_probability(self):
        result = evaluate_anomaly_state(
            make_rows(),
            features=("a", "b"),
            horizon=10,
            anomaly_quantile=0.90,
            move_quantile=0.80,
            min_anomaly_samples=100,
        )

        self.assertIsNotNone(result)

        self.assertGreater(
            result.anomaly_large_move_probability,
            result.normal_large_move_probability,
        )

    def test_anomaly_can_be_non_directional(self):
        result = evaluate_anomaly_state(
            make_rows(),
            features=("a", "b"),
            horizon=10,
            anomaly_quantile=0.90,
            move_quantile=0.80,
            min_anomaly_samples=100,
        )

        self.assertLess(
            result.directional_effect,
            0.15,
        )

        self.assertGreater(
            result.large_move_effect,
            0.05,
        )

    def test_directional_anomaly_is_detected(self):
        result = evaluate_anomaly_state(
            make_directional_rows(),
            features=("a", "b"),
            horizon=10,
            anomaly_quantile=0.90,
            min_anomaly_samples=100,
        )

        self.assertGreater(
            result.anomaly_mean,
            result.normal_mean,
        )

        self.assertEqual(
            result.direction,
            1,
        )

    def test_cross_family_ancestry_retained(self):
        result = evaluate_anomaly_state(
            make_rows(),
            features=("a", "b"),
            horizon=10,
            min_anomaly_samples=100,
        )

        self.assertIn(
            "PRICE",
            result.ancestry,
        )

        self.assertIn(
            "LEVEL1_SNAPSHOT",
            result.ancestry,
        )

    def test_discovery_ranks_planted_group(self):
        discoveries = discover_anomaly_states(
            make_rows(),
            feature_groups=(
                ("a", "b"),
                ("a", "noise"),
            ),
            horizons=(10,),
            anomaly_quantiles=(0.90,),
            move_quantile=0.80,
            min_anomaly_samples=100,
            min_effect=0.01,
            max_results=10,
        )

        self.assertTrue(discoveries)

        self.assertEqual(
            set(
                discoveries[
                    0
                ].features
            ),
            {"a", "b"},
        )

    def test_constant_features_are_safe(self):
        rows = [
            UnifiedResearchRow(
                symbol="S",
                minute=i,
                price=100.0,
                features={
                    "a": 1.0,
                    "b": 1.0,
                },
                forward_returns={
                    10: float(i),
                },
                feature_ancestry={
                    "a": ("PRICE",),
                    "b": ("PRICE",),
                },
            )
            for i in range(100)
        ]

        result = evaluate_anomaly_state(
            rows,
            features=("a", "b"),
            horizon=10,
            min_anomaly_samples=10,
        )

        self.assertIsNone(result)

    def test_empty_features_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            evaluate_anomaly_state(
                make_rows(),
                features=(),
                horizon=10,
            )

    def test_feature_count_is_bounded(self):
        with self.assertRaises(
            ValueError
        ):
            evaluate_anomaly_state(
                make_rows(),
                features=tuple(
                    f"x{i}"
                    for i in range(9)
                ),
                horizon=10,
                max_features=8,
            )

    def test_invalid_anomaly_quantile_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            evaluate_anomaly_state(
                make_rows(),
                features=("a", "b"),
                horizon=10,
                anomaly_quantile=0.40,
            )

    def test_insufficient_samples_rejected(self):
        result = evaluate_anomaly_state(
            make_rows()[:20],
            features=("a", "b"),
            horizon=10,
            min_anomaly_samples=30,
        )

        self.assertIsNone(result)

    def test_discovery_is_bounded(self):
        discoveries = discover_anomaly_states(
            make_rows(),
            feature_groups=(
                ("a", "b"),
                ("a", "noise"),
                ("b", "noise"),
            ),
            horizons=(10,),
            anomaly_quantiles=(
                0.90,
                0.95,
            ),
            min_anomaly_samples=50,
            min_effect=0.0,
            max_results=2,
        )

        self.assertLessEqual(
            len(discoveries),
            2,
        )

    def test_ids_are_deterministic(self):
        rows = make_rows()

        first = evaluate_anomaly_state(
            rows,
            features=("a", "b"),
            horizon=10,
        )

        second = evaluate_anomaly_state(
            rows,
            features=("a", "b"),
            horizon=10,
        )

        self.assertEqual(
            first.discovery_id,
            second.discovery_id,
        )


if __name__ == "__main__":
    unittest.main()
