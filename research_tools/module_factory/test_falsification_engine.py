import math
import random
import unittest

from research_tools.module_factory.falsification_engine import (
    EvaluationObservation,
    build_validation_evidence,
    calculate_falsification_diagnostics,
)
from research_tools.module_factory.hypothesis_protocol import (
    DataDeclaration,
    DatasetRole,
    ValidationPolicy,
    freeze_hypothesis,
    judge_validation,
    make_specification,
)


def make_frozen(
    *,
    direction=1,
    tests_considered=10,
):
    spec = make_specification(
        scientist="synthetic",
        discovery_id="synthetic:test",
        target="forward_return",
        horizon=10,
        features=("signal",),
        parameters={
            "threshold": 1.0,
        },
        direction=direction,
        ancestry=("PRICE",),
        provenance=("autonomous",),
        discovery_dataset_ids=(
            "discovery",
        ),
        multiple_testing_family=(
            "synthetic_family"
        ),
        tests_considered=(
            tests_considered
        ),
        min_samples=30,
        min_events=10,
    )

    return freeze_hypothesis(
        spec
    )


def independent_observations(
    seed=20260902,
    n=500,
    mean_effect=0.003,
):
    rng = random.Random(seed)

    return [
        EvaluationObservation(
            symbol=f"S{i % 50:02d}",
            time_bucket=f"T{i % 20:02d}",
            effect=(
                mean_effect
                + rng.gauss(
                    0.0,
                    0.01,
                )
            ),
            event=(
                i % 2 == 0
            ),
        )
        for i in range(n)
    ]


class FalsificationEngineTests(
    unittest.TestCase
):
    def test_primary_effect_is_empirical_mean(self):
        observations = [
            EvaluationObservation(
                symbol="A",
                time_bucket="T1",
                effect=0.01,
            ),
            EvaluationObservation(
                symbol="B",
                time_bucket="T2",
                effect=0.03,
            ),
        ]

        result = (
            calculate_falsification_diagnostics(
                observations,
                neighborhood_effects=(
                    0.015,
                    0.020,
                ),
                tests_considered=1,
                estimated_cost_bps=0.0,
            )
        )

        self.assertAlmostEqual(
            result.primary_effect,
            0.02,
        )

    def test_cost_is_subtracted_in_effect_direction(self):
        result = (
            calculate_falsification_diagnostics(
                independent_observations(
                    mean_effect=0.003
                ),
                neighborhood_effects=(
                    0.0025,
                    0.0028,
                ),
                tests_considered=1,
                estimated_cost_bps=10.0,
            )
        )

        self.assertAlmostEqual(
            result.net_effect,
            result.primary_effect
            - 0.001,
        )

    def test_symbol_concentration_detected(self):
        observations = [
            EvaluationObservation(
                symbol=(
                    "DOMINANT"
                    if i < 80
                    else f"S{i}"
                ),
                time_bucket=f"T{i}",
                effect=0.01,
            )
            for i in range(100)
        ]

        result = (
            calculate_falsification_diagnostics(
                observations,
                neighborhood_effects=(
                    0.01,
                ),
                tests_considered=1,
                estimated_cost_bps=0.0,
            )
        )

        self.assertEqual(
            result.symbol_concentration,
            0.80,
        )

    def test_time_concentration_detected(self):
        observations = [
            EvaluationObservation(
                symbol=f"S{i}",
                time_bucket=(
                    "OPEN"
                    if i < 70
                    else f"T{i}"
                ),
                effect=0.01,
            )
            for i in range(100)
        ]

        result = (
            calculate_falsification_diagnostics(
                observations,
                neighborhood_effects=(
                    0.01,
                ),
                tests_considered=1,
                estimated_cost_bps=0.0,
            )
        )

        self.assertEqual(
            result.time_concentration,
            0.70,
        )

    def test_positive_serial_dependence_reduces_ess(self):
        rng = random.Random(7)

        effects = []
        value = 0.0

        for _ in range(500):
            value = (
                0.90 * value
                + rng.gauss(
                    0.0,
                    0.01,
                )
            )

            effects.append(value)

        observations = [
            EvaluationObservation(
                symbol=f"S{i % 30}",
                time_bucket=f"T{i % 20}",
                effect=effect,
            )
            for i, effect
            in enumerate(effects)
        ]

        result = (
            calculate_falsification_diagnostics(
                observations,
                neighborhood_effects=(
                    0.001,
                ),
                tests_considered=1,
                estimated_cost_bps=0.0,
            )
        )

        self.assertGreater(
            result.lag1_dependence,
            0.70,
        )

        self.assertLess(
            result.effective_sample_size,
            150,
        )

    def test_independent_series_keeps_most_ess(self):
        result = (
            calculate_falsification_diagnostics(
                independent_observations(),
                neighborhood_effects=(
                    0.002,
                    0.003,
                ),
                tests_considered=1,
                estimated_cost_bps=0.0,
            )
        )

        self.assertGreater(
            result.effective_sample_size,
            350,
        )

    def test_parameter_stability_rewards_neighbors(self):
        result = (
            calculate_falsification_diagnostics(
                independent_observations(
                    mean_effect=0.01
                ),
                neighborhood_effects=(
                    0.009,
                    0.011,
                    0.008,
                ),
                tests_considered=1,
                estimated_cost_bps=0.0,
            )
        )

        self.assertGreater(
            result.parameter_stability,
            0.75,
        )

    def test_parameter_sign_reversal_hurts_stability(self):
        result = (
            calculate_falsification_diagnostics(
                independent_observations(
                    mean_effect=0.01
                ),
                neighborhood_effects=(
                    -0.01,
                    0.009,
                    -0.008,
                ),
                tests_considered=1,
                estimated_cost_bps=0.0,
            )
        )

        self.assertLess(
            result.parameter_stability,
            0.40,
        )

    def test_multiple_testing_adjustment_is_conservative(self):
        one = (
            calculate_falsification_diagnostics(
                independent_observations(),
                neighborhood_effects=(
                    0.002,
                ),
                tests_considered=1,
                estimated_cost_bps=0.0,
            )
        )

        many = (
            calculate_falsification_diagnostics(
                independent_observations(),
                neighborhood_effects=(
                    0.002,
                ),
                tests_considered=100,
                estimated_cost_bps=0.0,
            )
        )

        self.assertGreaterEqual(
            many.adjusted_p_value,
            one.adjusted_p_value,
        )

    def test_build_evidence_uses_frozen_test_count(self):
        frozen = make_frozen(
            tests_considered=100
        )

        evidence = (
            build_validation_evidence(
                frozen,
                dataset_id="validation",
                observations=(
                    independent_observations()
                ),
                neighborhood_effects=(
                    0.002,
                    0.003,
                ),
                estimated_cost_bps=2.0,
            )
        )

        self.assertEqual(
            evidence.hypothesis_id,
            frozen.hypothesis_id,
        )

        self.assertEqual(
            evidence.specification_hash,
            frozen.specification_hash,
        )

        self.assertIsNotNone(
            evidence.effective_sample_size
        )

        self.assertIsNotNone(
            evidence.net_effect
        )

    def test_low_ess_can_fail_validation(self):
        frozen = make_frozen(
            tests_considered=1
        )

        rng = random.Random(12)

        observations = []
        value = 0.01

        for i in range(300):
            value = (
                0.97 * value
                + rng.gauss(
                    0.0,
                    0.001,
                )
            )

            observations.append(
                EvaluationObservation(
                    symbol=f"S{i % 50}",
                    time_bucket=f"T{i % 20}",
                    effect=value,
                )
            )

        evidence = (
            build_validation_evidence(
                frozen,
                dataset_id="validation",
                observations=observations,
                neighborhood_effects=(
                    0.005,
                    0.006,
                ),
                estimated_cost_bps=0.0,
            )
        )

        dataset = DataDeclaration(
            dataset_id="validation",
            role=DatasetRole.VALIDATION,
            sealed=False,
        )

        decision = judge_validation(
            frozen,
            dataset,
            evidence,
            policy=ValidationPolicy(
                min_abs_effect=0.0,
                max_adjusted_p_value=None,
                max_symbol_concentration=1.0,
                max_time_concentration=1.0,
                min_parameter_stability=0.0,
                min_effective_sample_size=50.0,
                require_positive_net_effect=False,
            ),
        )

        self.assertIn(
            "insufficient_effective_sample",
            decision.reasons,
        )

    def test_cost_can_kill_directional_hypothesis(self):
        frozen = make_frozen(
            direction=1,
            tests_considered=1,
        )

        observations = (
            independent_observations(
                mean_effect=0.0002
            )
        )

        evidence = (
            build_validation_evidence(
                frozen,
                dataset_id="validation",
                observations=observations,
                neighborhood_effects=(
                    0.0002,
                    0.0003,
                ),
                estimated_cost_bps=5.0,
            )
        )

        dataset = DataDeclaration(
            dataset_id="validation",
            role=DatasetRole.VALIDATION,
            sealed=False,
        )

        decision = judge_validation(
            frozen,
            dataset,
            evidence,
            policy=ValidationPolicy(
                min_abs_effect=0.0,
                max_adjusted_p_value=None,
                max_symbol_concentration=1.0,
                max_time_concentration=1.0,
                min_parameter_stability=0.0,
                min_effective_sample_size=0.0,
                require_positive_net_effect=True,
            ),
        )

        self.assertIn(
            "cost_failure",
            decision.reasons,
        )

    def test_empty_observations_rejected(self):
        with self.assertRaises(
            ValueError
        ):
            calculate_falsification_diagnostics(
                (),
                neighborhood_effects=(
                    0.01,
                ),
                tests_considered=1,
                estimated_cost_bps=0.0,
            )


if __name__ == "__main__":
    unittest.main()
