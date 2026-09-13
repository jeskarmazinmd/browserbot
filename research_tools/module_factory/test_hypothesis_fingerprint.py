import unittest

from research_tools.module_factory.hypothesis_fingerprint import (
    feature_family,
    feature_timescale_bucket,
    fingerprint_conditional,
    fingerprint_regime,
    fingerprint_distribution,
    fingerprint_residual,
    fingerprint_time_series,
    fingerprint_anomaly,
)


class HypothesisFingerprintTests(unittest.TestCase):
    def test_return_windows_share_momentum_family(self):
        self.assertEqual(
            feature_family("return_30"),
            feature_family("return_60"),
        )
        self.assertEqual(
            feature_family("return_30"),
            "return",
        )

    def test_relative_return_is_distinct_family(self):
        self.assertEqual(
            feature_family(
                "spy_relative_return_30"
            ),
            "spy_relative_return",
        )
        self.assertNotEqual(
            feature_family("return_30"),
            feature_family(
                "spy_relative_return_30"
            ),
        )

    def test_nearby_medium_windows_share_bucket(self):
        self.assertEqual(
            feature_timescale_bucket(
                "return_20"
            ),
            feature_timescale_bucket(
                "return_30"
            ),
        )

    def test_long_window_is_separate_bucket(self):
        self.assertNotEqual(
            feature_timescale_bucket(
                "return_20"
            ),
            feature_timescale_bucket(
                "return_60"
            ),
        )

    def test_conditional_near_duplicates_share_family(self):
        a = fingerprint_conditional(
            signal_feature="return_30",
            state_feature="kurtosis_60",
            horizon=20,
            state_direction="low",
            preferred_sign=1,
        )
        b = fingerprint_conditional(
            signal_feature="return_20",
            state_feature="kurtosis_60",
            horizon=20,
            state_direction="low",
            preferred_sign=1,
        )

        self.assertEqual(
            a.family_key,
            b.family_key,
        )

    def test_conditional_opposite_state_is_distinct(self):
        low = fingerprint_conditional(
            signal_feature="return_30",
            state_feature="kurtosis_60",
            horizon=20,
            state_direction="low",
            preferred_sign=1,
        )
        high = fingerprint_conditional(
            signal_feature="return_30",
            state_feature="kurtosis_60",
            horizon=20,
            state_direction="high",
            preferred_sign=1,
        )

        self.assertNotEqual(
            low.family_key,
            high.family_key,
        )

    def test_regime_quantile_variants_share_family(self):
        a = fingerprint_regime(
            feature="return_30",
            regime_feature="kurtosis_60",
            horizon=20,
            dominant_regime="low",
            direction_low=1,
            direction_high=-1,
            sign_reversal=True,
        )
        b = fingerprint_regime(
            feature="return_20",
            regime_feature="kurtosis_60",
            horizon=20,
            dominant_regime="low",
            direction_low=1,
            direction_high=-1,
            sign_reversal=True,
        )

        self.assertEqual(
            a.family_key,
            b.family_key,
        )

    def test_regime_reversal_is_distinct_from_nonreversal(self):
        reversal = fingerprint_regime(
            feature="return_30",
            regime_feature="kurtosis_60",
            horizon=20,
            dominant_regime="low",
            direction_low=1,
            direction_high=-1,
            sign_reversal=True,
        )
        one_sided = fingerprint_regime(
            feature="return_30",
            regime_feature="kurtosis_60",
            horizon=20,
            dominant_regime="low",
            direction_low=1,
            direction_high=1,
            sign_reversal=False,
        )

        self.assertNotEqual(
            reversal.family_key,
            one_sided.family_key,
        )

    def test_distribution_return_variants_share_family(self):
        a = fingerprint_distribution(
            feature="return_30",
            horizon=20,
            dominant_effect="large_move",
            direction_low=-1,
            direction_high=1,
        )
        b = fingerprint_distribution(
            feature="return_20",
            horizon=20,
            dominant_effect="large_move",
            direction_low=-1,
            direction_high=1,
        )

        self.assertEqual(
            a.family_key,
            b.family_key,
        )

    def test_residual_controls_are_canonicalized(self):
        a = fingerprint_residual(
            candidate="skew_60",
            controls=(
                "return_30",
                "kurtosis_60",
            ),
            horizon=20,
            direction=-1,
        )
        b = fingerprint_residual(
            candidate="skew_60",
            controls=(
                "kurtosis_60",
                "return_30",
            ),
            horizon=20,
            direction=-1,
        )

        self.assertEqual(
            a.family_key,
            b.family_key,
        )

    def test_lag_neighborhoods_share_family(self):
        a = fingerprint_time_series(
            feature="acceleration_20",
            horizon=20,
            best_lag=8,
            direction=1,
            sign_change=True,
        )
        b = fingerprint_time_series(
            feature="acceleration_20",
            horizon=20,
            best_lag=10,
            direction=1,
            sign_change=True,
        )

        self.assertEqual(
            a.family_key,
            b.family_key,
        )

    def test_lag_zero_and_lag_ten_are_distinct(self):
        a = fingerprint_time_series(
            feature="acceleration_20",
            horizon=20,
            best_lag=0,
            direction=1,
            sign_change=False,
        )
        b = fingerprint_time_series(
            feature="acceleration_20",
            horizon=20,
            best_lag=10,
            direction=1,
            sign_change=False,
        )

        self.assertNotEqual(
            a.family_key,
            b.family_key,
        )

    def test_anomaly_feature_order_is_irrelevant(self):
        a = fingerprint_anomaly(
            features=(
                "kurtosis_20",
                "return_60",
            ),
            horizon=20,
            dominant_effect="large_move",
            direction=-1,
        )
        b = fingerprint_anomaly(
            features=(
                "return_60",
                "kurtosis_20",
            ),
            horizon=20,
            dominant_effect="large_move",
            direction=-1,
        )

        self.assertEqual(
            a.family_key,
            b.family_key,
        )

    def test_family_key_is_deterministic(self):
        a = fingerprint_conditional(
            signal_feature="return_30",
            state_feature="kurtosis_60",
            horizon=20,
            state_direction="low",
            preferred_sign=1,
        )
        b = fingerprint_conditional(
            signal_feature="return_30",
            state_feature="kurtosis_60",
            horizon=20,
            state_direction="low",
            preferred_sign=1,
        )

        self.assertEqual(
            a.family_key,
            b.family_key,
        )


if __name__ == "__main__":
    unittest.main()
