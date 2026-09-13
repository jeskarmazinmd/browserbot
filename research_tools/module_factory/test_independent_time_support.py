import unittest
from datetime import datetime, timedelta, timezone

from research_tools.module_factory.feature_matrix import FeatureRow
from research_tools.module_factory.research_row_adapter import from_feature_row

from research_tools.module_factory.conditional_scientist import (
    analyze_condition,
)
from research_tools.module_factory.interaction_scientist import (
    evaluate_interaction,
)
from research_tools.module_factory.regime_scientist import (
    evaluate_regime,
)
from research_tools.module_factory.distribution_scientist import (
    evaluate_distribution_state,
)
from research_tools.module_factory.residual_scientist import (
    evaluate_residual_relationship,
)
from research_tools.module_factory.time_series_scientist import (
    evaluate_lag_structure,
)
from research_tools.module_factory.anomaly_scientist import (
    evaluate_anomaly_state,
)


BASE = datetime(
    2026, 1, 2, 14, 30,
    tzinfo=timezone.utc,
)


def feature_rows(
    *,
    minutes=40,
    symbols=20,
):
    rows = []

    for minute_index in range(minutes):
        minute = BASE + timedelta(
            minutes=minute_index
        )

        for symbol_index in range(symbols):
            x = (
                symbol_index
                - symbols / 2
            ) / max(symbols, 1)

            state = (
                minute_index
                / max(minutes - 1, 1)
            )

            rows.append(
                FeatureRow(
                    symbol=f"S{symbol_index:03d}",
                    minute=minute,
                    price=100.0,
                    features={
                        "signal": x,
                        "state": state,
                        "control": (
                            x * 0.2
                            + state * 0.1
                        ),
                        "other": (
                            (symbol_index % 7)
                            / 7.0
                        ),
                    },
                    forward_returns={
                        20: (
                            x
                            if state < 0.5
                            else -x
                        ),
                    },
                )
            )

    return rows


def unified_rows(**kwargs):
    return [
        from_feature_row(row)
        for row in feature_rows(**kwargs)
    ]


class IndependentTimeSupportTests(
    unittest.TestCase
):
    def test_conditional_counts_unique_subset_minutes(
        self,
    ):
        result = analyze_condition(
            feature_rows(),
            signal_feature="signal",
            state_feature="state",
            horizon=20,
            state_direction="low",
            state_fraction=0.25,
            min_conditional_observations=20,
        )

        self.assertIsNotNone(result)

        # 25% low-state tail of 40 market minutes.
        self.assertEqual(
            result.independent_time_units,
            10,
        )

    def test_interaction_counts_usable_minutes(
        self,
    ):
        result = evaluate_interaction(
            unified_rows(),
            left="signal",
            right="other",
            operation="multiply",
            horizon=20,
            min_samples=20,
        )

        self.assertIsNotNone(result)
        self.assertEqual(
            result.independent_time_units,
            40,
        )

    def test_regime_uses_weaker_tail_support(
        self,
    ):
        result = evaluate_regime(
            unified_rows(),
            feature="signal",
            regime_feature="state",
            horizon=20,
            low_quantile=0.25,
            high_quantile=0.75,
            min_samples_per_regime=20,
        )

        self.assertIsNotNone(result)

        self.assertEqual(
            result.independent_time_units,
            10,
        )

    def test_distribution_uses_weaker_tail_support(
        self,
    ):
        result = evaluate_distribution_state(
            unified_rows(),
            feature="state",
            horizon=20,
            tail_quantile=0.25,
            min_tail_samples=20,
        )

        self.assertIsNotNone(result)

        self.assertEqual(
            result.independent_time_units,
            10,
        )

    def test_residual_counts_usable_minutes(
        self,
    ):
        result = evaluate_residual_relationship(
            unified_rows(),
            candidate="signal",
            controls=(
                "control",
                "other",
            ),
            horizon=20,
            min_samples=20,
        )

        self.assertIsNotNone(result)

        self.assertEqual(
            result.independent_time_units,
            40,
        )

    def test_time_series_counts_winning_target_minutes(
        self,
    ):
        result = evaluate_lag_structure(
            unified_rows(
                minutes=50,
                symbols=20,
            ),
            feature="signal",
            horizon=20,
            lags=(0, 1, 3),
            min_samples=20,
        )

        self.assertIsNotNone(result)

        best = next(
            item
            for item in result.evidence
            if item.lag == result.best_lag
        )

        self.assertEqual(
            result.independent_time_units,
            best.independent_time_units,
        )

        self.assertGreater(
            result.independent_time_units,
            0,
        )

        self.assertLessEqual(
            result.independent_time_units,
            50,
        )

    def test_anomaly_counts_anomaly_subset_minutes(
        self,
    ):
        result = evaluate_anomaly_state(
            unified_rows(),
            features=(
                "signal",
                "state",
            ),
            horizon=20,
            anomaly_quantile=0.75,
            min_anomaly_samples=20,
        )

        self.assertIsNotNone(result)

        self.assertGreater(
            result.independent_time_units,
            0,
        )

        self.assertLessEqual(
            result.independent_time_units,
            40,
        )

        # It must describe the selected anomaly state,
        # not simply report all available minutes.
        self.assertLess(
            result.independent_time_units,
            40,
        )


if __name__ == "__main__":
    unittest.main()
