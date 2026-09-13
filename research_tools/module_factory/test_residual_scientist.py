import random
import unittest

from research_tools.module_factory.research_rows import (
    UnifiedResearchRow,
)
from research_tools.module_factory.residual_scientist import (
    discover_residual_relationships,
    evaluate_residual_relationship,
)


def make_rows(
    seed=20260902,
    candidate_coefficient=0.18,
):
    rng = random.Random(seed)

    rows = []

    for i in range(2000):
        market = rng.gauss(
            0.0,
            1.0,
        )

        # Candidate contains a lot of market exposure,
        # plus an independent component.
        independent = rng.gauss(
            0.0,
            1.0,
        )

        candidate = (
            2.5 * market
            + independent
        )

        noise_feature = rng.gauss(
            0.0,
            1.0,
        )

        # Raw outcome is dominated by a NEGATIVE market
        # relationship. Candidate's independent component
        # contains a positive residual relationship.
        outcome = (
            -1.0 * market
            + candidate_coefficient
            * independent
            + rng.gauss(
                0.0,
                0.08,
            )
        )

        rows.append(
            UnifiedResearchRow(
                symbol=f"S{i % 40:02d}",
                minute=i,
                price=100.0,
                features={
                    "market": market,
                    "candidate":
                        candidate,
                    "noise":
                        noise_feature,
                },
                forward_returns={
                    10: outcome,
                },
                feature_ancestry={
                    "market": (
                        "MARKET_CONTEXT",
                    ),
                    "candidate": (
                        "LEVEL1_SNAPSHOT",
                    ),
                    "noise": (
                        "DERIVED",
                    ),
                },
            )
        )

    return rows


class ResidualScientistTests(
    unittest.TestCase
):
    def test_hidden_residual_relationship_is_found(self):
        result = (
            evaluate_residual_relationship(
                make_rows(),
                candidate="candidate",
                controls=("market",),
                horizon=10,
                min_samples=100,
            )
        )

        self.assertIsNotNone(result)

        self.assertGreater(
            result.residual_correlation,
            0.80,
        )

    def test_raw_relationship_can_have_opposite_sign(self):
        result = (
            evaluate_residual_relationship(
                make_rows(),
                candidate="candidate",
                controls=("market",),
                horizon=10,
                min_samples=100,
            )
        )

        self.assertLess(
            result.raw_correlation,
            -0.50,
        )

        self.assertGreater(
            result.residual_correlation,
            0.80,
        )

        self.assertEqual(
            result.direction,
            1,
        )

    def test_noise_does_not_become_strong_residual(self):
        result = (
            evaluate_residual_relationship(
                make_rows(),
                candidate="noise",
                controls=("market",),
                horizon=10,
                min_samples=100,
            )
        )

        self.assertIsNotNone(result)

        self.assertLess(
            abs(
                result.residual_correlation
            ),
            0.10,
        )

    def test_cross_source_ancestry_retained(self):
        result = (
            evaluate_residual_relationship(
                make_rows(),
                candidate="candidate",
                controls=("market",),
                horizon=10,
                min_samples=100,
            )
        )

        self.assertIn(
            "LEVEL1_SNAPSHOT",
            result.ancestry,
        )

        self.assertIn(
            "MARKET_CONTEXT",
            result.ancestry,
        )

    def test_discovery_ranks_planted_candidate(self):
        discoveries = (
            discover_residual_relationships(
                make_rows(),
                candidate_names=(
                    "candidate",
                    "noise",
                ),
                control_names=(
                    "market",
                ),
                horizons=(10,),
                min_samples=100,
                min_residual_correlation=0.10,
                max_results=10,
            )
        )

        self.assertTrue(
            discoveries
        )

        self.assertEqual(
            discoveries[0].candidate,
            "candidate",
        )

        self.assertGreater(
            discoveries[
                0
            ].residual_correlation,
            0.80,
        )

    def test_negative_residual_direction_is_empirical(self):
        result = (
            evaluate_residual_relationship(
                make_rows(
                    seed=77,
                    candidate_coefficient=-0.18,
                ),
                candidate="candidate",
                controls=("market",),
                horizon=10,
                min_samples=100,
            )
        )

        self.assertLess(
            result.residual_correlation,
            -0.80,
        )

        self.assertEqual(
            result.direction,
            -1,
        )

    def test_candidate_cannot_be_control(self):
        with self.assertRaises(
            ValueError
        ):
            evaluate_residual_relationship(
                make_rows(),
                candidate="candidate",
                controls=(
                    "market",
                    "candidate",
                ),
                horizon=10,
            )

    def test_control_count_is_bounded(self):
        with self.assertRaises(
            ValueError
        ):
            evaluate_residual_relationship(
                make_rows(),
                candidate="candidate",
                controls=tuple(
                    f"x{i}"
                    for i in range(9)
                ),
                horizon=10,
                max_controls=8,
            )

    def test_insufficient_sample_rejected(self):
        result = (
            evaluate_residual_relationship(
                make_rows()[:10],
                candidate="candidate",
                controls=("market",),
                horizon=10,
                min_samples=30,
            )
        )

        self.assertIsNone(result)

    def test_discovery_is_bounded(self):
        discoveries = (
            discover_residual_relationships(
                make_rows(),
                candidate_names=(
                    "candidate",
                    "noise",
                ),
                control_names=(
                    "market",
                ),
                horizons=(10,),
                min_samples=100,
                min_residual_correlation=0.0,
                max_results=1,
            )
        )

        self.assertLessEqual(
            len(discoveries),
            1,
        )

    def test_ids_are_deterministic(self):
        rows = make_rows()

        first = (
            evaluate_residual_relationship(
                rows,
                candidate="candidate",
                controls=("market",),
                horizon=10,
            )
        )

        second = (
            evaluate_residual_relationship(
                rows,
                candidate="candidate",
                controls=("market",),
                horizon=10,
            )
        )

        self.assertEqual(
            first.discovery_id,
            second.discovery_id,
        )


if __name__ == "__main__":
    unittest.main()
