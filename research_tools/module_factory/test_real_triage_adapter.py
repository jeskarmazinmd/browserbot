import unittest

from research_tools.module_factory.real_triage_adapter import (
    concept_for_record,
    triage_candidate_from_record,
)


class RealTriageAdapterTests(unittest.TestCase):
    def test_cross_sectional_uses_minutes_as_time_support(self):
        item = {
            "feature": "return_60",
            "horizon": 20,
            "preferred_sign": 1,
            "score": 2.5,
            "minutes": 17,
        }

        candidate = triage_candidate_from_record(
            "cross_sectional",
            item,
        )

        self.assertEqual(
            candidate.independent_time_units,
            17,
        )

    def test_measured_time_support_is_used(self):
        item = {
            "candidate": "skew_60",
            "controls": ["return_60"],
            "horizon": 20,
            "direction": -1,
            "score": 25.5,
            "incremental_clarity": 0.076,
            "independent_time_units": 23,
        }

        candidate = triage_candidate_from_record(
            "residual",
            item,
        )

        self.assertEqual(
            candidate.independent_time_units,
            23,
        )

    def test_legacy_missing_time_support_fails_conservatively(self):
        item = {
            "candidate": "skew_60",
            "controls": ["return_60"],
            "horizon": 20,
            "direction": -1,
            "score": 25.5,
            "incremental_clarity": 0.076,
        }

        candidate = triage_candidate_from_record(
            "residual",
            item,
        )

        self.assertEqual(
            candidate.independent_time_units,
            0,
        )

    def test_regime_sign_reversal_maps_to_sign_change(self):
        item = {
            "feature": "return_30",
            "regime_feature": "kurtosis_60",
            "dominant_regime": "low",
            "direction_low": 1,
            "direction_high": -1,
            "sign_reversal": True,
            "horizon": 20,
            "score": 78.0,
            "independent_time_units": 17,
        }

        candidate = triage_candidate_from_record(
            "regime",
            item,
        )

        self.assertTrue(
            candidate.sign_change
        )

    def test_residual_uses_incremental_clarity(self):
        item = {
            "candidate": "skew_60",
            "controls": [
                "kurtosis_60",
                "return_60",
            ],
            "horizon": 20,
            "direction": -1,
            "score": 25.5,
            "incremental_clarity": 0.076,
        }

        candidate = triage_candidate_from_record(
            "residual",
            item,
        )

        self.assertEqual(
            candidate.incremental_evidence,
            0.076,
        )

    def test_time_series_uses_incremental_lag_edge(self):
        item = {
            "feature": "acceleration_20",
            "horizon": 20,
            "best_lag": 10,
            "direction": 1,
            "score": 29.4,
            "incremental_lag_edge": 0.071,
            "sign_change": True,
        }

        candidate = triage_candidate_from_record(
            "time_series",
            item,
        )

        self.assertEqual(
            candidate.incremental_evidence,
            0.071,
        )
        self.assertTrue(
            candidate.sign_change
        )

    def test_interaction_exact_market_reduction_is_flagged(self):
        item = {
            "left": "return_30",
            "right": "spy_relative_return_30",
            "operation": "subtract",
            "horizon": 10,
            "direction": -1,
            "score": 4.47,
            "incremental_edge": 0.142,
        }

        candidate = triage_candidate_from_record(
            "interaction",
            item,
        )

        self.assertTrue(
            candidate.exact_redundant
        )

    def test_return_kurtosis_conditional_and_regime_share_concept(self):
        conditional = {
            "signal_feature": "return_30",
            "state_feature": "kurtosis_60",
            "state_direction": "low",
            "horizon": 20,
            "preferred_sign": 1,
            "score": 4.4,
            "improvement": 0.27,
        }

        regime = {
            "feature": "return_30",
            "regime_feature": "kurtosis_60",
            "dominant_regime": "low",
            "direction_low": 1,
            "direction_high": -1,
            "sign_reversal": True,
            "horizon": 20,
            "score": 78.0,
        }

        self.assertEqual(
            concept_for_record(
                "conditional",
                conditional,
            ),
            concept_for_record(
                "regime",
                regime,
            ),
        )

    def test_residual_skew_is_distinct_concept(self):
        skew = {
            "candidate": "skew_60",
            "controls": ["return_60"],
            "horizon": 20,
            "direction": -1,
            "score": 25.5,
            "incremental_clarity": 0.076,
        }

        regime = {
            "feature": "return_30",
            "regime_feature": "kurtosis_60",
            "dominant_regime": "low",
            "direction_low": 1,
            "direction_high": -1,
            "sign_reversal": True,
            "horizon": 20,
            "score": 78.0,
        }

        self.assertNotEqual(
            concept_for_record(
                "residual",
                skew,
            ),
            concept_for_record(
                "regime",
                regime,
            ),
        )


if __name__ == "__main__":
    unittest.main()
