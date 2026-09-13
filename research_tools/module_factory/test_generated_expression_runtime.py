import unittest

from research_tools.module_factory.generated_strategy import (
    GeneratedStrategy,
    GeneratedStrategySpec,
)


class GeneratedExpressionRuntimeTests(unittest.TestCase):

    def spec(self, **changes):
        values = {
            "module_id": "FM_EXPR",
            "hypothesis_id": "hypothesis:expr",
            "specification_hash": "hash-expr",
            "scientist": "factory",
            "feature": "",
            "horizon": 20,
            "direction": 1,
            "expression": {
                "op": "subtract",
                "left": {
                    "op": "feature",
                    "name": "return_30",
                },
                "right": {
                    "op": "feature",
                    "name": "spy_relative_return_30",
                },
            },
            "predicate": {
                "op": "lt",
                "left": {
                    "op": "feature",
                    "name": "kurtosis_60",
                },
                "right": {
                    "op": "constant",
                    "value": 0.5,
                },
            },
        }
        values.update(changes)
        return GeneratedStrategySpec(**values)

    def test_expression_and_predicate_emit(self):
        strategy = GeneratedStrategy(self.spec())
        signal = strategy.evaluate_row(
            symbol="AAPL",
            timestamp="t1",
            features={
                "return_30": 2.0,
                "spy_relative_return_30": 0.5,
                "kurtosis_60": 0.2,
            },
        )
        self.assertIsNotNone(signal)
        self.assertAlmostEqual(
            signal.data["feature_value"],
            1.5,
        )

    def test_predicate_blocks_signal(self):
        strategy = GeneratedStrategy(self.spec())
        signal = strategy.evaluate_row(
            symbol="AAPL",
            timestamp="t1",
            features={
                "return_30": 2.0,
                "spy_relative_return_30": 0.5,
                "kurtosis_60": 0.8,
            },
        )
        self.assertIsNone(signal)

    def test_missing_feature_fails_closed(self):
        strategy = GeneratedStrategy(self.spec())
        signal = strategy.evaluate_row(
            symbol="AAPL",
            timestamp="t1",
            features={
                "return_30": 2.0,
                "kurtosis_60": 0.2,
            },
        )
        self.assertIsNone(signal)

    def test_invalid_operator_rejected(self):
        with self.assertRaises(ValueError):
            self.spec(
                expression={
                    "op": "python_eval",
                    "value": "__import__('os')",
                }
            )

    def test_legacy_contract_still_works(self):
        strategy = GeneratedStrategy(
            GeneratedStrategySpec(
                module_id="FM_OLD",
                hypothesis_id="hypothesis:old",
                specification_hash="hash-old",
                scientist="old",
                feature="return_30",
                horizon=20,
                direction=1,
                threshold=1.0,
            )
        )
        self.assertIsNotNone(
            strategy.evaluate_row(
                symbol="AAPL",
                timestamp="t1",
                features={"return_30": 2.0},
            )
        )
        self.assertIsNone(
            strategy.evaluate_row(
                symbol="AAPL",
                timestamp="t2",
                features={"return_30": 0.5},
            )
        )


if __name__ == "__main__":
    unittest.main()
