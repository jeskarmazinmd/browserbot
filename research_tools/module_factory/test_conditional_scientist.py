import unittest
from datetime import datetime, timedelta, timezone

from research_tools.module_factory.conditional_scientist import (
    analyze_condition,
    discover,
)
from research_tools.module_factory.feature_matrix import FeatureRow


class ConditionalScientistTests(unittest.TestCase):
    def _rows(self):
        rows = []

        for day in (2, 3, 4):
            base = datetime(
                2026, 1, day, 14, 30,
                tzinfo=timezone.utc,
            )

            for i in range(500):
                signal = (
                    (i % 100) - 50
                ) / 50.0

                state = (
                    (i * 37) % 100
                ) / 100.0

                noise = (
                    (
                        i * 17
                        + day * 13
                    )
                    % 101
                    - 50
                ) / 50.0

                # Signal only becomes strongly predictive
                # in the highest 20% of state.
                if state >= 0.80:
                    future = (
                        signal * 0.8
                        + noise * 0.02
                    )
                else:
                    future = (
                        noise * 0.25
                    )

                rows.append(
                    FeatureRow(
                        symbol=f"S{i % 100}",
                        minute=(
                            base
                            + timedelta(minutes=i)
                        ),
                        price=100.0,
                        features={
                            "signal": signal,
                            "state": state,
                            "noise": noise,
                        },
                        forward_returns={
                            20: future,
                        },
                    )
                )

        return rows

    def test_high_state_finds_hidden_signal(self):
        result = analyze_condition(
            self._rows(),
            signal_feature="signal",
            state_feature="state",
            horizon=20,
            state_direction="high",
        )

        self.assertIsNotNone(result)

        self.assertGreater(
            result.conditional_correlation,
            0.90,
        )

        self.assertGreater(
            result.improvement,
            0.30,
        )

        self.assertEqual(
            result.preferred_sign,
            1,
        )

    def test_low_state_is_weaker(self):
        rows = self._rows()

        high = analyze_condition(
            rows,
            signal_feature="signal",
            state_feature="state",
            horizon=20,
            state_direction="high",
        )

        low = analyze_condition(
            rows,
            signal_feature="signal",
            state_feature="state",
            horizon=20,
            state_direction="low",
        )

        self.assertIsNotNone(high)
        self.assertIsNotNone(low)

        self.assertGreater(
            abs(
                high.conditional_correlation
            ),
            abs(
                low.conditional_correlation
            ),
        )

    def test_discovery_ranks_planted_condition(self):
        results = discover(
            self._rows(),
            signal_features=[
                "signal",
                "noise",
            ],
            state_features=["state"],
            horizons=(20,),
        )

        self.assertEqual(
            results[0].signal_feature,
            "signal",
        )

        self.assertEqual(
            results[0].state_direction,
            "high",
        )

    def test_condition_is_bounded_subset(self):
        result = analyze_condition(
            self._rows(),
            signal_feature="signal",
            state_feature="state",
            horizon=20,
            state_direction="high",
        )

        self.assertLess(
            result.conditional_observations,
            result.observations,
        )

        self.assertGreater(
            result.conditional_observations,
            0,
        )

    def test_requires_valid_direction(self):
        with self.assertRaises(ValueError):
            analyze_condition(
                self._rows(),
                signal_feature="signal",
                state_feature="state",
                horizon=20,
                state_direction="middle",
            )


if __name__ == "__main__":
    unittest.main()
