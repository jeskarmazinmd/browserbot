import unittest

from research_tools.module_factory.generated_strategy import (
    GeneratedStrategy,
    GeneratedStrategySpec,
)


class GeneratedStrategyTests(unittest.TestCase):
    def make_spec(self, **overrides):
        values = {
            "module_id": "FM_TEST",
            "hypothesis_id": "hypothesis:test",
            "specification_hash": "hash-test",
            "scientist": "regime",
            "feature": "return_30",
            "horizon": 20,
            "direction": 1,
            "threshold": None,
        }
        values.update(overrides)
        return GeneratedStrategySpec(**values)

    def test_fail_closed_flags(self):
        strategy = GeneratedStrategy(
            self.make_spec()
        )

        self.assertTrue(strategy.PAPER_ONLY)
        self.assertFalse(
            strategy.LIVE_ORDER_PLACEMENT
        )

    def test_emits_paper_signal(self):
        strategy = GeneratedStrategy(
            self.make_spec()
        )

        signal = strategy.evaluate_row(
            symbol="AAPL",
            timestamp="2026-09-03T15:00:00Z",
            features={
                "return_30": 1.25,
            },
        )

        self.assertIsNotNone(signal)
        self.assertEqual(
            signal.strategy_id,
            "FM_TEST",
        )
        self.assertTrue(
            signal.data["factory_generated"]
        )
        self.assertTrue(
            signal.data["paper_only"]
        )
        self.assertFalse(
            signal.data["live_order_placement"]
        )

    def test_missing_feature_does_not_signal(self):
        strategy = GeneratedStrategy(
            self.make_spec()
        )

        self.assertIsNone(
            strategy.evaluate_row(
                symbol="AAPL",
                timestamp="now",
                features={},
            )
        )

    def test_threshold_is_enforced(self):
        strategy = GeneratedStrategy(
            self.make_spec(
                threshold=2.0,
            )
        )

        self.assertIsNone(
            strategy.evaluate_row(
                symbol="AAPL",
                timestamp="now",
                features={
                    "return_30": 1.0,
                },
            )
        )

        self.assertIsNotNone(
            strategy.evaluate_row(
                symbol="AAPL",
                timestamp="now",
                features={
                    "return_30": 3.0,
                },
            )
        )

    def test_direction_must_be_binary(self):
        with self.assertRaises(ValueError):
            self.make_spec(direction=0)


if __name__ == "__main__":
    unittest.main()
