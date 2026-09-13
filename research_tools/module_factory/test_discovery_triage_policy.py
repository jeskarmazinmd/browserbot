import unittest

from research_tools.module_factory.discovery_triage_policy import (
    TriageCandidate,
    select_diverse_candidates,
)


class DiscoveryTriagePolicyTests(unittest.TestCase):
    def candidate(
        self,
        *,
        candidate_id,
        scientist,
        concept,
        score,
        independent_time_units=100,
        incremental_evidence=None,
        sign_change=False,
        exact_redundant=False,
    ):
        return TriageCandidate(
            candidate_id=candidate_id,
            scientist=scientist,
            concept=concept,
            score=score,
            independent_time_units=(
                independent_time_units
            ),
            incremental_evidence=(
                incremental_evidence
            ),
            sign_change=sign_change,
            exact_redundant=(
                exact_redundant
            ),
        )

    def test_hard_shortlist_cap(self):
        candidates = [
            self.candidate(
                candidate_id=f"c{i}",
                scientist="generic",
                concept=f"concept-{i}",
                score=100 - i,
            )
            for i in range(20)
        ]

        selected = select_diverse_candidates(
            candidates,
            max_candidates=8,
        )

        self.assertLessEqual(
            len(selected),
            8,
        )

    def test_exact_redundancy_is_rejected(self):
        candidates = [
            self.candidate(
                candidate_id="fake",
                scientist="interaction",
                concept="market-return",
                score=1000,
                exact_redundant=True,
            ),
            self.candidate(
                candidate_id="real",
                scientist="residual",
                concept="residual-skew",
                score=1,
            ),
        ]

        selected = select_diverse_candidates(
            candidates,
        )

        ids = {
            item.candidate_id
            for item in selected
        }

        self.assertNotIn("fake", ids)
        self.assertIn("real", ids)

    def test_same_concept_does_not_fill_batch(self):
        candidates = [
            self.candidate(
                candidate_id="conditional",
                scientist="conditional",
                concept="return-kurtosis-state",
                score=10,
            ),
            self.candidate(
                candidate_id="regime",
                scientist="regime",
                concept="return-kurtosis-state",
                score=20,
            ),
            self.candidate(
                candidate_id="anomaly",
                scientist="anomaly",
                concept="return-kurtosis-state",
                score=15,
            ),
            self.candidate(
                candidate_id="skew",
                scientist="residual",
                concept="residual-skew",
                score=5,
            ),
        ]

        selected = select_diverse_candidates(
            candidates,
            max_per_concept=1,
        )

        concepts = [
            item.concept
            for item in selected
        ]

        self.assertEqual(
            concepts.count(
                "return-kurtosis-state"
            ),
            1,
        )

        ids = {
            item.candidate_id
            for item in selected
        }

        self.assertIn("regime", ids)
        self.assertIn("skew", ids)

    def test_zero_incremental_residual_is_rejected(self):
        candidates = [
            self.candidate(
                candidate_id="raw-return",
                scientist="residual",
                concept="return-residual",
                score=100,
                incremental_evidence=0.0,
            ),
            self.candidate(
                candidate_id="skew",
                scientist="residual",
                concept="residual-skew",
                score=20,
                incremental_evidence=0.07,
            ),
        ]

        selected = select_diverse_candidates(
            candidates,
            min_incremental_evidence=0.02,
        )

        ids = {
            item.candidate_id
            for item in selected
        }

        self.assertNotIn(
            "raw-return",
            ids,
        )
        self.assertIn(
            "skew",
            ids,
        )

    def test_small_time_support_is_penalized(self):
        broad = self.candidate(
            candidate_id="broad",
            scientist="generic",
            concept="momentum",
            score=5,
            independent_time_units=100,
        )

        concentrated = self.candidate(
            candidate_id="concentrated",
            scientist="cross_sectional",
            concept="cross-sectional-momentum",
            score=5,
            independent_time_units=17,
        )

        selected = select_diverse_candidates(
            [concentrated, broad],
            max_candidates=2,
        )

        self.assertEqual(
            selected[0].candidate_id,
            "broad",
        )

    def test_sign_change_can_preserve_lag_discovery(self):
        ordinary = self.candidate(
            candidate_id="ordinary-lag",
            scientist="time_series",
            concept="return-lag",
            score=50,
            incremental_evidence=0.01,
            sign_change=False,
        )

        reversal = self.candidate(
            candidate_id="lag-reversal",
            scientist="time_series",
            concept="acceleration-lag-reversal",
            score=20,
            incremental_evidence=0.01,
            sign_change=True,
        )

        selected = select_diverse_candidates(
            [ordinary, reversal],
            min_incremental_evidence=0.02,
        )

        ids = {
            item.candidate_id
            for item in selected
        }

        self.assertNotIn(
            "ordinary-lag",
            ids,
        )
        self.assertIn(
            "lag-reversal",
            ids,
        )

    def test_distinct_scientific_concepts_survive(self):
        candidates = [
            self.candidate(
                candidate_id="regime",
                scientist="regime",
                concept="return-kurtosis-state",
                score=80,
            ),
            self.candidate(
                candidate_id="skew",
                scientist="residual",
                concept="residual-skew",
                score=25,
                incremental_evidence=0.08,
            ),
            self.candidate(
                candidate_id="acceleration",
                scientist="time_series",
                concept="acceleration-lag-reversal",
                score=29,
                incremental_evidence=0.01,
                sign_change=True,
            ),
            self.candidate(
                candidate_id="cross-section",
                scientist="cross_sectional",
                concept="cross-sectional-return",
                score=2.5,
                independent_time_units=17,
            ),
            self.candidate(
                candidate_id="anomaly",
                scientist="anomaly",
                concept="large-move-anomaly",
                score=28,
            ),
        ]

        selected = select_diverse_candidates(
            candidates,
            max_candidates=8,
        )

        ids = {
            item.candidate_id
            for item in selected
        }

        self.assertEqual(
            ids,
            {
                "regime",
                "skew",
                "acceleration",
                "cross-section",
                "anomaly",
            },
        )


if __name__ == "__main__":
    unittest.main()
