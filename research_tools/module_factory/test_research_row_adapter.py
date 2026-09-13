import unittest

from research_tools.module_factory.research_row_adapter import (
    from_feature_row,
)


class FakeFeatureRow:
    def __init__(self):
        self.symbol = "AAA"
        self.minute = 123
        self.price = 100.0
        self.features = {
            "return_5": 0.01,
            "volatility_20": 0.02,
        }
        self.forward_returns = {
            10: 0.03,
        }


class ResearchRowAdapterTests(
    unittest.TestCase
):
    def test_old_feature_row_adapts(self):
        row = from_feature_row(
            FakeFeatureRow()
        )

        self.assertEqual(
            row.symbol,
            "AAA",
        )

        self.assertAlmostEqual(
            row.feature("return_5"),
            0.01,
        )

        self.assertEqual(
            row.ancestry("return_5"),
            ("PRICE",),
        )

    def test_microstructure_can_merge(self):
        row = from_feature_row(
            FakeFeatureRow(),
            extra_features={
                "depth_imbalance": 0.5,
                "spread_bps": 12.0,
            },
        )

        self.assertAlmostEqual(
            row.feature(
                "depth_imbalance"
            ),
            0.5,
        )

        self.assertIn(
            "LEVEL1_SNAPSHOT",
            row.ancestry(
                "depth_imbalance"
            ),
        )

        self.assertEqual(
            len(row.features),
            4,
        )

    def test_collision_is_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            from_feature_row(
                FakeFeatureRow(),
                extra_features={
                    "return_5": 999.0,
                },
            )

    def test_unknown_extra_feature_is_derived(self):
        row = from_feature_row(
            FakeFeatureRow(),
            extra_features={
                "experimental_x": 1.0,
            },
        )

        self.assertEqual(
            row.ancestry(
                "experimental_x"
            ),
            ("DERIVED",),
        )


if __name__ == "__main__":
    unittest.main()
