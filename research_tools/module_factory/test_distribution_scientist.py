import random
import unittest

from research_tools.module_factory.distribution_scientist import (
    discover_distribution_states,
    evaluate_distribution_state,
)
from research_tools.module_factory.research_rows import (
    UnifiedResearchRow,
)


def make_rows(
    seed=20260902,
):
    rng = random.Random(seed)

    rows = []

    for i in range(2000):
        state = rng.uniform(
            -1.0,
            1.0,
        )

        noise = rng.gauss(
            0.0,
            1.0,
        )

        # Most states have small, symmetric outcomes.
        outcome = rng.gauss(
            0.0,
            0.01,
        )

        # High state produces large moves but keeps
        # directional mean near zero.
        if state > 0.75:
            magnitude = (
                0.10
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
                symbol=f"S{i % 30:02d}",
                minute=i,
                price=100.0,
                features={
                    "state": state,
                    "noise": noise,
                },
                forward_returns={
                    10: outcome,
                },
                feature_ancestry={
                    "state": (
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
    seed=77,
):
    rng = random.Random(seed)

    rows = []

    for i in range(1800):
        state = rng.uniform(
            -1.0,
            1.0,
        )

        if state < -0.70:
            outcome = (
                -0.06
                + rng.gauss(
                    0.0,
                    0.015,
                )
            )
        elif state > 0.70:
            outcome = (
                0.06
                + rng.gauss(
                    0.0,
                    0.015,
                )
            )
        else:
            outcome = rng.gauss(
                0.0,
                0.02,
            )

        rows.append(
            UnifiedResearchRow(
                symbol=f"S{i % 25:02d}",
                minute=i,
                price=100.0,
                features={
                    "state": state,
                },
                forward_returns={
                    10: outcome,
                },
                feature_ancestry={
                    "state": ("PRICE",),
                },
            )
        )

    return rows


class DistributionScientistTests(
    unittest.TestCase
):
    def test_large_move_state_is_found(self):
        result = (
            evaluate_distribution_state(
                make_rows(),
                feature="state",
                horizon=10,
                tail_quantile=0.20,
                move_quantile=0.80,
                min_tail_samples=100,
            )
        )

        self.assertIsNotNone(result)

        self.assertGreater(
            result.high_large_move_probability,
            result.low_large_move_probability
            + 0.50,
        )

        self.assertEqual(
            result.dominant_effect,
            "large_move",
        )

    def test_large_move_signal_need_not_have_mean_direction(self):
        result = (
            evaluate_distribution_state(
                make_rows(),
                feature="state",
                horizon=10,
                tail_quantile=0.20,
                move_quantile=0.80,
                min_tail_samples=100,
            )
        )

        self.assertLess(
            abs(result.high_mean),
            0.02,
        )

        self.assertGreater(
            result.move_asymmetry,
            0.50,
        )

    def test_directional_tail_asymmetry_is_found(self):
        result = (
            evaluate_distribution_state(
                make_directional_rows(),
                feature="state",
                horizon=10,
                tail_quantile=0.20,
                min_tail_samples=100,
            )
        )

        self.assertLess(
            result.low_mean,
            -0.04,
        )

        self.assertGreater(
            result.high_mean,
            0.04,
        )

        self.assertEqual(
            result.direction_low,
            -1,
        )

        self.assertEqual(
            result.direction_high,
            1,
        )

    def test_ancestry_retained(self):
        result = (
            evaluate_distribution_state(
                make_rows(),
                feature="state",
                horizon=10,
                min_tail_samples=100,
            )
        )

        self.assertEqual(
            result.ancestry,
            (
                "LEVEL1_SNAPSHOT",
            ),
        )

    def test_discovery_ranks_planted_state(self):
        discoveries = (
            discover_distribution_states(
                make_rows(),
                feature_names=(
                    "state",
                    "noise",
                ),
                horizons=(10,),
                tail_quantiles=(
                    0.20,
                ),
                move_quantile=0.80,
                min_tail_samples=100,
                min_effect=0.10,
                max_results=10,
            )
        )

        self.assertTrue(
            discoveries
        )

        self.assertEqual(
            discoveries[0].feature,
            "state",
        )

        self.assertEqual(
            discoveries[
                0
            ].dominant_effect,
            "large_move",
        )

    def test_invalid_tail_quantile_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            evaluate_distribution_state(
                make_rows(),
                feature="state",
                horizon=10,
                tail_quantile=0.60,
            )

    def test_invalid_move_quantile_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            evaluate_distribution_state(
                make_rows(),
                feature="state",
                horizon=10,
                move_quantile=0.40,
            )

    def test_insufficient_samples_rejected(self):
        result = (
            evaluate_distribution_state(
                make_rows()[:20],
                feature="state",
                horizon=10,
                min_tail_samples=30,
            )
        )

        self.assertIsNone(result)

    def test_discovery_is_bounded(self):
        discoveries = (
            discover_distribution_states(
                make_rows(),
                feature_names=(
                    "state",
                    "noise",
                ),
                horizons=(10,),
                tail_quantiles=(
                    0.10,
                    0.20,
                    0.25,
                ),
                min_tail_samples=50,
                min_effect=0.0,
                max_results=2,
            )
        )

        self.assertLessEqual(
            len(discoveries),
            2,
        )

    def test_ids_are_deterministic(self):
        rows = make_rows()

        first = (
            evaluate_distribution_state(
                rows,
                feature="state",
                horizon=10,
                tail_quantile=0.20,
            )
        )

        second = (
            evaluate_distribution_state(
                rows,
                feature="state",
                horizon=10,
                tail_quantile=0.20,
            )
        )

        self.assertEqual(
            first.discovery_id,
            second.discovery_id,
        )


if __name__ == "__main__":
    unittest.main()
