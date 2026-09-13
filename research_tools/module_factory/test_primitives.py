import unittest

from research_tools.module_factory.primitives import (
    base_feature_specs,
    generate_interaction_specs,
    generate_signal_specs,
)


class PrimitiveTests(unittest.TestCase):
    def test_feature_ids_are_unique(self):
        features = base_feature_specs()
        ids = [x.feature_id for x in features]
        self.assertEqual(len(ids), len(set(ids)))

    def test_vocabulary_spans_multiple_mathematical_families(self):
        families = {x.family for x in base_feature_specs()}

        self.assertTrue(
            {
                "return",
                "volatility",
                "range_position",
                "sign_persistence",
                "acceleration",
                "autocorrelation",
                "distribution",
                "relative_return",
            }.issubset(families)
        )

    def test_signal_generation_is_agnostic_to_sign(self):
        signals = generate_signal_specs(
            quantiles=(0.10,),
            horizons=(20,),
        )

        directions = {x.direction for x in signals}
        self.assertEqual(directions, {"low", "high"})

    def test_signal_ids_are_unique(self):
        signals = generate_signal_specs()
        ids = [x.signal_id for x in signals]
        self.assertEqual(len(ids), len(set(ids)))

    def test_interactions_are_generated_mechanically(self):
        interactions = generate_interaction_specs(
            quantile=0.10,
            horizon=20,
            max_features=4,
        )

        # 4 choose 2 feature pairs x four directional combinations.
        self.assertEqual(len(interactions), 24)
        self.assertEqual(
            len({x.signal_id for x in interactions}),
            len(interactions),
        )


if __name__ == "__main__":
    unittest.main()
