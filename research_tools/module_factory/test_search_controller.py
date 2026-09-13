import unittest

from research_tools.module_factory.discovery_engine import Discovery
from research_tools.module_factory.expressions import ExpressionSpec
from research_tools.module_factory.search_controller import (
    SearchPolicy,
    build_candidates,
    expression_complexity,
    expression_lineage,
    mutate_parent,
    select_population,
)


def discovery(
    feature,
    score,
    *,
    consistency=1.0,
    worst=0.1,
    bh=False,
):
    return Discovery(
        feature=feature,
        horizon=10,
        score=score,
        sign_consistency=consistency,
        worst_day_edge=worst,
        bh_pass=bh,
    )


class SearchControllerTests(unittest.TestCase):
    def test_expression_complexity_and_lineage(self):
        e1 = ExpressionSpec(
            "subtract",
            "a",
            "b",
        )

        catalog = {
            e1.expression_id: e1,
        }

        self.assertEqual(
            expression_complexity(
                e1.expression_id,
                catalog,
            ),
            3,
        )

        lineage = expression_lineage(
            e1.expression_id,
            catalog,
        )

        self.assertIn("a", lineage)
        self.assertIn("b", lineage)

    def test_complexity_penalty_favors_simple_equal_edge(self):
        expression = ExpressionSpec(
            "multiply",
            "a",
            "b",
        )

        catalog = {
            expression.expression_id: expression,
        }

        candidates = build_candidates(
            [
                discovery("simple", 1.0),
                discovery(
                    expression.expression_id,
                    1.0,
                ),
            ],
            expression_catalog=catalog,
        )

        scores = {
            x.feature: x.search_score
            for x in candidates
        }

        self.assertGreater(
            scores["simple"],
            scores[expression.expression_id],
        )

    def test_population_is_bounded(self):
        candidates = build_candidates(
            [
                discovery(
                    f"f{i}",
                    float(i),
                    bh=(i % 3 == 0),
                )
                for i in range(100)
            ]
        )

        decision = select_population(
            candidates,
            policy=SearchPolicy(
                population_limit=20,
                elite_fraction=0.25,
                exploration_fraction=0.25,
            ),
        )

        self.assertEqual(
            len(decision.selected),
            20,
        )

    def test_exploration_is_preserved(self):
        candidates = build_candidates(
            [
                discovery(f"f{i}", float(i))
                for i in range(50)
            ]
        )

        decision = select_population(
            candidates,
            policy=SearchPolicy(
                population_limit=20,
                elite_fraction=0.25,
                exploration_fraction=0.25,
                seed=123,
            ),
        )

        self.assertGreater(
            decision.exploration_count,
            0,
        )

    def test_poor_consistency_is_rejected(self):
        candidates = build_candidates(
            [
                discovery(
                    "unstable",
                    10.0,
                    consistency=0.25,
                )
            ]
        )

        decision = select_population(candidates)

        self.assertEqual(
            len(decision.selected),
            0,
        )

        self.assertEqual(
            decision.rejected[0].reason,
            "poor_day_consistency",
        )

    def test_parent_mutation_creates_children(self):
        parent = build_candidates(
            [discovery("return_5", 1.0)]
        )[0]

        children = mutate_parent(
            parent,
            [
                "return_5",
                "volatility_10",
                "range_position_20",
            ],
            generation=2,
            seed=123,
        )

        self.assertGreater(
            len(children),
            2,
        )

        self.assertTrue(
            all(x.generation == 2 for x in children)
        )


if __name__ == "__main__":
    unittest.main()
