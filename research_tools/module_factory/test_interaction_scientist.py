import math
import random
import unittest

from research_tools.module_factory.interaction_scientist import (
    discover_interactions,
    evaluate_interaction,
)
from research_tools.module_factory.research_rows import (
    UnifiedResearchRow,
)


def row(
    i,
    *,
    x,
    y,
    noise,
    outcome,
):
    return UnifiedResearchRow(
        symbol=f"S{i % 20:02d}",
        minute=i,
        price=100.0,
        features={
            "x": x,
            "y": y,
            "noise": noise,
        },
        forward_returns={
            10: outcome,
        },
        feature_ancestry={
            "x": ("PRICE",),
            "y": (
                "LEVEL1_SNAPSHOT",
            ),
            "noise": ("DERIVED",),
        },
    )


class InteractionScientistTests(
    unittest.TestCase
):
    def planted_rows(self):
        rng = random.Random(20260902)

        rows = []

        for i in range(800):
            x = rng.gauss(0.0, 1.0)
            y = rng.gauss(0.0, 1.0)
            noise = rng.gauss(
                0.0,
                1.0,
            )

            # Neither x nor y alone should explain much.
            # Their interaction does.
            outcome = (
                0.08 * x * y
                + rng.gauss(
                    0.0,
                    0.025,
                )
            )

            rows.append(
                row(
                    i,
                    x=x,
                    y=y,
                    noise=noise,
                    outcome=outcome,
                )
            )

        return rows

    def test_planted_interaction_is_found(self):
        result = evaluate_interaction(
            self.planted_rows(),
            left="x",
            right="y",
            operation="multiply",
            horizon=10,
            min_samples=100,
        )

        self.assertIsNotNone(result)

        self.assertGreater(
            abs(
                result.interaction_correlation
            ),
            0.8,
        )

        self.assertGreater(
            result.incremental_edge,
            0.6,
        )

    def test_components_are_much_weaker(self):
        result = evaluate_interaction(
            self.planted_rows(),
            left="x",
            right="y",
            operation="multiply",
            horizon=10,
            min_samples=100,
        )

        self.assertLess(
            abs(result.left_correlation),
            0.15,
        )

        self.assertLess(
            abs(result.right_correlation),
            0.15,
        )

    def test_cross_family_ancestry_retained(self):
        result = evaluate_interaction(
            self.planted_rows(),
            left="x",
            right="y",
            operation="multiply",
            horizon=10,
        )

        self.assertIn(
            "PRICE",
            result.ancestry,
        )

        self.assertIn(
            "LEVEL1_SNAPSHOT",
            result.ancestry,
        )

    def test_discovery_ranks_planted_pair(self):
        discoveries = discover_interactions(
            self.planted_rows(),
            feature_names=(
                "x",
                "y",
                "noise",
            ),
            horizons=(10,),
            operations=("multiply",),
            min_samples=100,
            min_incremental_edge=0.05,
            max_results=10,
        )

        self.assertTrue(discoveries)

        top = discoveries[0]

        self.assertEqual(
            {top.left, top.right},
            {"x", "y"},
        )

    def test_direction_is_empirical(self):
        rows = []

        rng = random.Random(11)

        for i in range(500):
            x = rng.gauss(0.0, 1.0)
            y = rng.gauss(0.0, 1.0)

            rows.append(
                row(
                    i,
                    x=x,
                    y=y,
                    noise=0.0,
                    outcome=(
                        -0.1 * x * y
                        + rng.gauss(
                            0.0,
                            0.02,
                        )
                    ),
                )
            )

        result = evaluate_interaction(
            rows,
            left="x",
            right="y",
            operation="multiply",
            horizon=10,
        )

        self.assertEqual(
            result.direction,
            -1,
        )

    def test_insufficient_sample_rejected(self):
        result = evaluate_interaction(
            self.planted_rows()[:10],
            left="x",
            right="y",
            operation="multiply",
            horizon=10,
            min_samples=30,
        )

        self.assertIsNone(result)

    def test_divide_by_zero_is_safe(self):
        rows = [
            row(
                i,
                x=float(i),
                y=0.0,
                noise=0.0,
                outcome=0.0,
            )
            for i in range(100)
        ]

        result = evaluate_interaction(
            rows,
            left="x",
            right="y",
            operation="divide",
            horizon=10,
            min_samples=30,
        )

        self.assertIsNone(result)

    def test_discovery_is_bounded(self):
        discoveries = discover_interactions(
            self.planted_rows(),
            feature_names=(
                "x",
                "y",
                "noise",
            ),
            horizons=(10,),
            min_samples=100,
            min_incremental_edge=0.0,
            max_results=2,
        )

        self.assertLessEqual(
            len(discoveries),
            2,
        )

    def test_discovery_ids_are_deterministic(self):
        rows = self.planted_rows()

        first = evaluate_interaction(
            rows,
            left="x",
            right="y",
            operation="multiply",
            horizon=10,
        )

        second = evaluate_interaction(
            rows,
            left="y",
            right="x",
            operation="multiply",
            horizon=10,
        )

        self.assertEqual(
            first.discovery_id,
            second.discovery_id,
        )


if __name__ == "__main__":
    unittest.main()
