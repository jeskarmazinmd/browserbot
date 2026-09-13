import math
import unittest
from datetime import datetime, timedelta, timezone

from research_tools.cascade_reversal_study import Bar
from research_tools.module_factory.feature_matrix import (
    build_feature_matrix,
)
from research_tools.module_factory.primitives import (
    base_feature_specs,
)


def make_series(start: float, count: int, step: float):
    base = datetime(
        2026, 1, 2, 14, 30, tzinfo=timezone.utc
    )

    result = []

    for i in range(count):
        price = start + i * step

        result.append(
            Bar(
                minute=base + timedelta(minutes=i),
                open=price,
                high=price + 0.01,
                low=price - 0.01,
                close=price,
            )
        )

    return result


class FeatureMatrixTests(unittest.TestCase):
    def setUp(self):
        self.bars = {
            "ABC": make_series(100.0, 100, 0.05),
            "XYZ": make_series(50.0, 100, -0.01),
            "SPY": make_series(500.0, 100, 0.02),
        }

    def test_matrix_builds_rows(self):
        rows = build_feature_matrix(self.bars)
        self.assertGreater(len(rows), 0)

    def test_matrix_contains_entire_declared_vocabulary(self):
        rows = build_feature_matrix(self.bars)
        declared = {x.name for x in base_feature_specs()}

        self.assertEqual(
            declared,
            set(rows[0].features),
        )

    def test_forward_outcomes_exist(self):
        rows = build_feature_matrix(self.bars)
        self.assertEqual(
            set(rows[0].forward_returns),
            {1, 5, 10, 20},
        )

    def test_return_feature_has_expected_sign(self):
        rows = build_feature_matrix(self.bars)

        abc = next(row for row in rows if row.symbol == "ABC")
        xyz = next(row for row in rows if row.symbol == "XYZ")

        self.assertGreater(abc.features["return_5"], 0)
        self.assertLess(xyz.features["return_5"], 0)

    def test_features_are_finite_when_spy_is_available(self):
        rows = build_feature_matrix(self.bars)

        for value in rows[0].features.values():
            self.assertTrue(math.isfinite(value))


if __name__ == "__main__":
    unittest.main()
