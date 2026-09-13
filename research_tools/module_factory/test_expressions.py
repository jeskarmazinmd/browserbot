import math
import unittest

from research_tools.module_factory.expressions import (
    ExpressionSpec,
    evaluate_expression,
    generation_one,
    generate_timescale_expressions,
)


class ExpressionTests(unittest.TestCase):
    def test_ids_are_deterministic(self):
        a = ExpressionSpec(
            operation="subtract",
            left="return_5",
            right="return_20",
        )

        b = ExpressionSpec(
            operation="subtract",
            left="return_5",
            right="return_20",
        )

        self.assertEqual(
            a.expression_id,
            b.expression_id,
        )

    def test_commutative_ids_are_canonical(self):
        a = ExpressionSpec(
            operation="multiply",
            left="a",
            right="b",
        )

        b = ExpressionSpec(
            operation="multiply",
            left="b",
            right="a",
        )

        self.assertEqual(
            a.expression_id,
            b.expression_id,
        )

    def test_directional_ids_differ(self):
        a = ExpressionSpec(
            operation="divide",
            left="a",
            right="b",
        )

        b = ExpressionSpec(
            operation="divide",
            left="b",
            right="a",
        )

        self.assertNotEqual(
            a.expression_id,
            b.expression_id,
        )

    def test_expression_evaluation(self):
        features = {
            "a": 6.0,
            "b": 2.0,
        }

        self.assertEqual(
            evaluate_expression(
                ExpressionSpec("subtract", "a", "b"),
                features,
            ),
            4.0,
        )

        self.assertEqual(
            evaluate_expression(
                ExpressionSpec("multiply", "a", "b"),
                features,
            ),
            12.0,
        )

        self.assertEqual(
            evaluate_expression(
                ExpressionSpec("divide", "a", "b"),
                features,
            ),
            3.0,
        )

    def test_divide_by_zero_is_nan(self):
        value = evaluate_expression(
            ExpressionSpec("divide", "a", "b"),
            {
                "a": 1.0,
                "b": 0.0,
            },
        )

        self.assertTrue(math.isnan(value))

    def test_timescale_generation(self):
        expressions = generate_timescale_expressions(
            [
                "return_1",
                "return_5",
                "return_20",
                "volatility_5",
                "volatility_20",
            ]
        )

        names = {x.name for x in expressions}

        self.assertIn(
            "(return_5-return_20)",
            names,
        )

        self.assertIn(
            "(volatility_5/volatility_20)",
            names,
        )

    def test_generation_is_unique(self):
        expressions = generation_one(
            [
                "return_1",
                "return_5",
                "volatility_5",
                "range_position_5",
            ]
        )

        ids = [x.expression_id for x in expressions]

        self.assertEqual(
            len(ids),
            len(set(ids)),
        )


if __name__ == "__main__":
    unittest.main()
