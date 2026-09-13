import unittest

from research_tools.module_factory.semantic_canonicalization import (
    CanonicalExpression,
    canonicalize_expression,
)


class SemanticCanonicalizationTests(unittest.TestCase):
    def test_commutative_addition_is_order_independent(self):
        a = canonicalize_expression(
            operation="add",
            left="return_30",
            right="kurtosis_20",
        )
        b = canonicalize_expression(
            operation="add",
            left="kurtosis_20",
            right="return_30",
        )
        self.assertEqual(a, b)

    def test_commutative_multiplication_is_order_independent(self):
        a = canonicalize_expression(
            operation="multiply",
            left="return_30",
            right="kurtosis_20",
        )
        b = canonicalize_expression(
            operation="multiply",
            left="kurtosis_20",
            right="return_30",
        )
        self.assertEqual(a, b)

    def test_subtraction_remains_directional(self):
        a = canonicalize_expression(
            operation="subtract",
            left="return_30",
            right="kurtosis_20",
        )
        b = canonicalize_expression(
            operation="subtract",
            left="kurtosis_20",
            right="return_30",
        )
        self.assertNotEqual(a, b)

    def test_relative_return_expands_to_own_minus_spy(self):
        result = canonicalize_expression(
            feature="spy_relative_return_30",
        )

        self.assertEqual(
            result,
            CanonicalExpression(
                operation="subtract",
                operands=(
                    CanonicalExpression(
                        operation="feature",
                        value="return_30",
                    ),
                    CanonicalExpression(
                        operation="market_return",
                        value="SPY",
                        lookback=30,
                    ),
                ),
            ),
        )

    def test_return_minus_relative_return_collapses_to_spy(self):
        result = canonicalize_expression(
            operation="subtract",
            left="return_30",
            right="spy_relative_return_30",
        )

        self.assertEqual(
            result,
            CanonicalExpression(
                operation="market_return",
                value="SPY",
                lookback=30,
            ),
        )

    def test_mismatched_lookbacks_do_not_false_collapse(self):
        result = canonicalize_expression(
            operation="subtract",
            left="return_30",
            right="spy_relative_return_60",
        )

        self.assertNotEqual(
            result,
            CanonicalExpression(
                operation="market_return",
                value="SPY",
                lookback=30,
            ),
        )

    def test_semantic_key_is_deterministic(self):
        a = canonicalize_expression(
            operation="subtract",
            left="return_30",
            right="spy_relative_return_30",
        )
        b = canonicalize_expression(
            operation="subtract",
            left="return_30",
            right="spy_relative_return_30",
        )

        self.assertEqual(a.semantic_key, b.semantic_key)


if __name__ == "__main__":
    unittest.main()
