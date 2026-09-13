import math
import unittest

from research_tools.module_factory.research_rows import (
    UnifiedResearchRow,
    feature_names,
    merge_feature_maps,
)


class ResearchRowsTests(
    unittest.TestCase
):
    def test_feature_and_outcome_access(self):
        row = UnifiedResearchRow(
            symbol="AAA",
            minute=1,
            price=100.0,
            features={
                "return_5": 0.01,
            },
            forward_returns={
                10: 0.02,
            },
            feature_ancestry={
                "return_5": (
                    "PRICE",
                ),
            },
        )

        self.assertAlmostEqual(
            row.feature("return_5"),
            0.01,
        )

        self.assertAlmostEqual(
            row.outcome(10),
            0.02,
        )

        self.assertEqual(
            row.ancestry("return_5"),
            ("PRICE",),
        )

    def test_missing_values_are_nan(self):
        row = UnifiedResearchRow(
            symbol="AAA",
            minute=1,
            price=100.0,
            features={},
            forward_returns={},
        )

        self.assertTrue(
            math.isnan(
                row.feature("missing")
            )
        )

        self.assertTrue(
            math.isnan(
                row.outcome(20)
            )
        )

    def test_feature_collision_is_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            merge_feature_maps(
                {"x": 1.0},
                {"x": 2.0},
            )

    def test_feature_names_union(self):
        rows = [
            UnifiedResearchRow(
                symbol="A",
                minute=1,
                price=1.0,
                features={"x": 1.0},
                forward_returns={},
            ),
            UnifiedResearchRow(
                symbol="B",
                minute=1,
                price=1.0,
                features={"y": 2.0},
                forward_returns={},
            ),
        ]

        self.assertEqual(
            feature_names(rows),
            ("x", "y"),
        )


if __name__ == "__main__":
    unittest.main()
