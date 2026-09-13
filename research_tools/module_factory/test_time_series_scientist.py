import random
import unittest

from research_tools.module_factory.research_rows import (
    UnifiedResearchRow,
)
from research_tools.module_factory.time_series_scientist import (
    discover_lag_structures,
    evaluate_lag_structure,
)


def make_rows(
    *,
    coefficient=0.10,
    planted_lag=3,
    seed=20260902,
):
    rng = random.Random(seed)

    rows = []

    symbols = [
        f"S{i:02d}"
        for i in range(20)
    ]

    length = 100

    for symbol in symbols:
        xs = [
            rng.gauss(0.0, 1.0)
            for _ in range(length)
        ]

        noises = [
            rng.gauss(0.0, 1.0)
            for _ in range(length)
        ]

        for minute in range(length):
            if minute >= planted_lag:
                signal = xs[
                    minute
                    - planted_lag
                ]
            else:
                signal = 0.0

            outcome = (
                coefficient * signal
                + rng.gauss(
                    0.0,
                    0.025,
                )
            )

            rows.append(
                UnifiedResearchRow(
                    symbol=symbol,
                    minute=minute,
                    price=100.0,
                    features={
                        "x": xs[minute],
                        "noise":
                            noises[minute],
                    },
                    forward_returns={
                        10: outcome,
                    },
                    feature_ancestry={
                        "x": ("PRICE",),
                        "noise":
                            ("DERIVED",),
                    },
                )
            )

    return rows


class TimeSeriesScientistTests(
    unittest.TestCase
):
    def test_delayed_effect_is_found(self):
        result = evaluate_lag_structure(
            make_rows(),
            feature="x",
            horizon=10,
            lags=(0, 1, 2, 3, 5),
            min_samples=100,
        )

        self.assertIsNotNone(result)

        self.assertEqual(
            result.best_lag,
            3,
        )

        self.assertGreater(
            result.best_correlation,
            0.8,
        )

    def test_contemporaneous_is_weak(self):
        result = evaluate_lag_structure(
            make_rows(),
            feature="x",
            horizon=10,
            lags=(0, 3),
            min_samples=100,
        )

        self.assertLess(
            abs(
                result.contemporaneous_correlation
            ),
            0.10,
        )

        self.assertGreater(
            result.incremental_lag_edge,
            0.7,
        )

    def test_negative_direction_is_empirical(self):
        result = evaluate_lag_structure(
            make_rows(
                coefficient=-0.10,
                planted_lag=2,
                seed=11,
            ),
            feature="x",
            horizon=10,
            lags=(0, 1, 2, 3),
            min_samples=100,
        )

        self.assertEqual(
            result.best_lag,
            2,
        )

        self.assertEqual(
            result.direction,
            -1,
        )

    def test_symbol_histories_do_not_mix(self):
        rows = []

        for i in range(60):
            rows.append(
                UnifiedResearchRow(
                    symbol="A",
                    minute=i,
                    price=100.0,
                    features={
                        "x": float(i),
                    },
                    forward_returns={
                        10: 0.0,
                    },
                    feature_ancestry={
                        "x": ("PRICE",),
                    },
                )
            )

            rows.append(
                UnifiedResearchRow(
                    symbol="B",
                    minute=i,
                    price=100.0,
                    features={
                        "x": float(
                            10000 + i
                        ),
                    },
                    forward_returns={
                        10: 0.0,
                    },
                    feature_ancestry={
                        "x": ("PRICE",),
                    },
                )
            )

        result = evaluate_lag_structure(
            rows,
            feature="x",
            horizon=10,
            lags=(1,),
            min_samples=30,
        )

        # Constant outcomes mean no valid
        # relationship should be produced.
        self.assertIsNone(result)

    def test_ancestry_retained(self):
        result = evaluate_lag_structure(
            make_rows(),
            feature="x",
            horizon=10,
            lags=(0, 3),
            min_samples=100,
        )

        self.assertEqual(
            result.ancestry,
            ("PRICE",),
        )

    def test_discovery_ranks_planted_feature(self):
        discoveries = (
            discover_lag_structures(
                make_rows(),
                feature_names=(
                    "x",
                    "noise",
                ),
                horizons=(10,),
                lags=(0, 1, 2, 3, 5),
                min_samples=100,
                min_best_correlation=0.10,
                max_results=10,
            )
        )

        self.assertTrue(discoveries)

        self.assertEqual(
            discoveries[0].feature,
            "x",
        )

        self.assertEqual(
            discoveries[0].best_lag,
            3,
        )

    def test_invalid_negative_lag_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            evaluate_lag_structure(
                make_rows(),
                feature="x",
                horizon=10,
                lags=(0, -1),
            )

    def test_empty_lags_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            evaluate_lag_structure(
                make_rows(),
                feature="x",
                horizon=10,
                lags=(),
            )

    def test_insufficient_sample_rejected(self):
        result = evaluate_lag_structure(
            make_rows()[:10],
            feature="x",
            horizon=10,
            lags=(0, 1),
            min_samples=30,
        )

        self.assertIsNone(result)

    def test_discovery_is_bounded(self):
        discoveries = (
            discover_lag_structures(
                make_rows(),
                feature_names=(
                    "x",
                    "noise",
                ),
                horizons=(10,),
                lags=(0, 1, 2, 3, 5),
                min_samples=100,
                min_best_correlation=0.0,
                max_results=1,
            )
        )

        self.assertLessEqual(
            len(discoveries),
            1,
        )

    def test_ids_are_deterministic(self):
        rows = make_rows()

        first = evaluate_lag_structure(
            rows,
            feature="x",
            horizon=10,
            lags=(0, 1, 2, 3),
        )

        second = evaluate_lag_structure(
            rows,
            feature="x",
            horizon=10,
            lags=(3, 2, 1, 0),
        )

        self.assertEqual(
            first.discovery_id,
            second.discovery_id,
        )


if __name__ == "__main__":
    unittest.main()
