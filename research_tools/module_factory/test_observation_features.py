import math
import unittest

from research_tools.module_factory.market_observations import (
    MarketObservation,
)
from research_tools.module_factory.observation_features import (
    MICROSTRUCTURE_BASE_FEATURES,
    ObservationFeatureState,
    base_microstructure_dict,
    generic_microstructure_feature_names,
)


def obs(
    symbol="AAA",
    *,
    bid=99.0,
    ask=101.0,
    bid_size=100.0,
    ask_size=100.0,
    last=100.0,
    mark=100.0,
    second=10,
):
    observed = (
        "2026-08-28T13:35:"
        f"{second:02d}+00:00"
    )

    observed_ms = (
        1787924110000
        + (second - 10) * 1000
    )

    return MarketObservation(
        market_minute_utc=(
            "2026-08-28T13:35:00+00:00"
        ),
        observed_at_utc=observed,
        symbol=symbol,
        price=last,
        last=last,
        mark=mark,
        bid=bid,
        ask=ask,
        last_size=100.0,
        bid_size=bid_size,
        ask_size=ask_size,
        quote_time_ms=(
            observed_ms - 1000
        ),
        trade_time_ms=(
            observed_ms - 2000
        ),
        bid_time_ms=(
            observed_ms - 1500
        ),
        ask_time_ms=(
            observed_ms - 1000
        ),
        regular_last=last,
        regular_trade_time_ms=(
            observed_ms - 2000
        ),
        extended_last=math.nan,
        last_mic="XNAS",
        bid_mic="XNAS",
        ask_mic="XNYS",
        realtime=True,
    )


class ObservationFeatureTests(
    unittest.TestCase
):
    def test_base_vocabulary_complete(self):
        values = base_microstructure_dict(
            obs()
        )

        self.assertEqual(
            set(values),
            set(
                MICROSTRUCTURE_BASE_FEATURES
            ),
        )

    def test_generic_names_are_unique(self):
        names = (
            generic_microstructure_feature_names()
        )

        self.assertEqual(
            len(names),
            len(set(names)),
        )

    def test_change_uses_same_symbol_history(self):
        state = ObservationFeatureState()

        first = state.transform(
            obs(
                bid=99.0,
                ask=101.0,
            )
        )

        second = state.transform(
            obs(
                bid=98.0,
                ask=102.0,
                second=11,
            )
        )

        self.assertTrue(
            math.isnan(
                first[
                    "spread_bps_change"
                ]
            )
        )

        self.assertGreater(
            second[
                "spread_bps_change"
            ],
            0.0,
        )

    def test_symbol_histories_are_isolated(self):
        state = ObservationFeatureState()

        state.transform(
            obs(
                symbol="AAA",
            )
        )

        other = state.transform(
            obs(
                symbol="BBB",
                second=11,
            )
        )

        self.assertTrue(
            math.isnan(
                other[
                    "spread_bps_change"
                ]
            )
        )

    def test_rolling_mean_appears_after_three(self):
        state = ObservationFeatureState()

        for second in (
            10,
            11,
        ):
            row = state.transform(
                obs(
                    second=second,
                )
            )

            self.assertTrue(
                math.isnan(
                    row[
                        "spread_bps_mean_3"
                    ]
                )
            )

        third = state.transform(
            obs(
                second=12,
            )
        )

        self.assertTrue(
            math.isfinite(
                third[
                    "spread_bps_mean_3"
                ]
            )
        )

    def test_rolling_std_detects_change(self):
        state = ObservationFeatureState()

        state.transform(
            obs(
                bid=99.0,
                ask=101.0,
                second=10,
            )
        )

        state.transform(
            obs(
                bid=99.5,
                ask=100.5,
                second=11,
            )
        )

        third = state.transform(
            obs(
                bid=98.0,
                ask=102.0,
                second=12,
            )
        )

        self.assertGreater(
            third[
                "spread_bps_std_3"
            ],
            0.0,
        )

    def test_depth_change_can_flip_sign(self):
        state = ObservationFeatureState()

        state.transform(
            obs(
                bid_size=300.0,
                ask_size=100.0,
            )
        )

        second = state.transform(
            obs(
                bid_size=100.0,
                ask_size=300.0,
                second=11,
            )
        )

        self.assertLess(
            second[
                "depth_imbalance_change"
            ],
            0.0,
        )

    def test_max_history_guard(self):
        with self.assertRaises(
            ValueError
        ):
            ObservationFeatureState(
                max_history=5
            )


if __name__ == "__main__":
    unittest.main()
