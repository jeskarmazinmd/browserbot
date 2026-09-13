import unittest
from dataclasses import FrozenInstanceError

from research_tools.module_factory.hypothesis_protocol import (
    DataDeclaration,
    DatasetRole,
    HypothesisState,
    ValidationEvidence,
    ValidationPolicy,
    assert_validation_access,
    freeze_hypothesis,
    judge_validation,
    make_specification,
    specification_hash,
    unseal_for_validation,
)


def make_spec(
    **overrides,
):
    values = dict(
        scientist="time_series",
        discovery_id=(
            "time-series:synthetic"
        ),
        target="forward_return",
        horizon=10,
        features=("displacement",),
        parameters={
            "lag": 5,
            "threshold": 0.20,
        },
        direction=-1,
        ancestry=(
            "PRICE",
            "TEMPORAL",
        ),
        provenance=(
            "autonomous",
        ),
        discovery_dataset_ids=(
            "discovery-day",
        ),
        multiple_testing_family=(
            "time_series_v1"
        ),
        tests_considered=240,
        min_samples=100,
        min_events=20,
    )

    values.update(overrides)

    return make_specification(
        **values
    )


def good_evidence(
    frozen,
    **overrides,
):
    values = dict(
        hypothesis_id=(
            frozen.hypothesis_id
        ),
        dataset_id=(
            "validation-day"
        ),
        specification_hash=(
            frozen.specification_hash
        ),
        n_samples=500,
        n_events=80,
        primary_effect=-0.18,
        adjusted_p_value=0.01,
        symbol_concentration=0.12,
        time_concentration=0.15,
        parameter_stability=0.80,
        estimated_cost_bps=4.0,
        effective_sample_size=400.0,
        net_effect=-0.1796,
        lag1_dependence=0.05,
        notes=(),
    )

    values.update(overrides)

    return ValidationEvidence(
        **values
    )


class HypothesisProtocolTests(
    unittest.TestCase
):
    def test_id_is_deterministic(self):
        first = make_spec()
        second = make_spec()

        self.assertEqual(
            first.hypothesis_id,
            second.hypothesis_id,
        )

    def test_parameter_order_does_not_change_id(self):
        first = make_spec(
            parameters={
                "lag": 5,
                "threshold": 0.20,
            }
        )

        second = make_spec(
            parameters={
                "threshold": 0.20,
                "lag": 5,
            }
        )

        self.assertEqual(
            first.hypothesis_id,
            second.hypothesis_id,
        )

    def test_changed_parameter_creates_new_hypothesis(self):
        first = make_spec(
            parameters={
                "lag": 5,
                "threshold": 0.20,
            }
        )

        second = make_spec(
            parameters={
                "lag": 3,
                "threshold": 0.20,
            }
        )

        self.assertNotEqual(
            first.hypothesis_id,
            second.hypothesis_id,
        )

    def test_changed_direction_creates_new_hypothesis(self):
        first = make_spec(
            direction=-1
        )

        second = make_spec(
            direction=1
        )

        self.assertNotEqual(
            first.hypothesis_id,
            second.hypothesis_id,
        )

    def test_frozen_specification_is_immutable(self):
        frozen = freeze_hypothesis(
            make_spec()
        )

        with self.assertRaises(
            FrozenInstanceError
        ):
            frozen.specification.horizon = 20

    def test_validation_data_cannot_open_before_freeze(self):
        dataset = DataDeclaration(
            dataset_id="validation-day",
            role=DatasetRole.VALIDATION,
            sealed=True,
        )

        with self.assertRaises(
            AttributeError
        ):
            # A specification is not a frozen hypothesis.
            unseal_for_validation(
                make_spec(),
                dataset,
            )

    def test_discovery_dataset_cannot_be_unseen_validation(self):
        frozen = freeze_hypothesis(
            make_spec()
        )

        dataset = DataDeclaration(
            dataset_id="discovery-day",
            role=DatasetRole.VALIDATION,
            sealed=True,
        )

        with self.assertRaises(
            PermissionError
        ):
            unseal_for_validation(
                frozen,
                dataset,
            )

    def test_validation_dataset_unseals_after_freeze(self):
        frozen = freeze_hypothesis(
            make_spec()
        )

        sealed = DataDeclaration(
            dataset_id="validation-day",
            role=DatasetRole.VALIDATION,
            sealed=True,
        )

        opened = (
            unseal_for_validation(
                frozen,
                sealed,
            )
        )

        self.assertFalse(
            opened.sealed
        )

        assert_validation_access(
            frozen,
            opened,
        )

    def test_sealed_dataset_rejected_by_judge(self):
        frozen = freeze_hypothesis(
            make_spec()
        )

        sealed = DataDeclaration(
            dataset_id="validation-day",
            role=DatasetRole.VALIDATION,
            sealed=True,
        )

        with self.assertRaises(
            PermissionError
        ):
            judge_validation(
                frozen,
                sealed,
                good_evidence(
                    frozen
                ),
            )

    def test_good_validation_passes(self):
        frozen = freeze_hypothesis(
            make_spec()
        )

        dataset = DataDeclaration(
            dataset_id="validation-day",
            role=DatasetRole.VALIDATION,
            sealed=False,
        )

        decision = judge_validation(
            frozen,
            dataset,
            good_evidence(
                frozen
            ),
        )

        self.assertTrue(
            decision.passed
        )

        self.assertEqual(
            decision.state,
            HypothesisState.VALIDATED_PASS,
        )

        self.assertEqual(
            decision.reasons,
            (),
        )

    def test_multiple_failures_are_recorded(self):
        frozen = freeze_hypothesis(
            make_spec()
        )

        dataset = DataDeclaration(
            dataset_id="validation-day",
            role=DatasetRole.VALIDATION,
            sealed=False,
        )

        decision = judge_validation(
            frozen,
            dataset,
            good_evidence(
                frozen,
                n_samples=20,
                n_events=2,
                primary_effect=0.01,
                adjusted_p_value=0.40,
                symbol_concentration=0.80,
                time_concentration=0.70,
                parameter_stability=0.20,
                effective_sample_size=5.0,
            ),
        )

        self.assertFalse(
            decision.passed
        )

        self.assertEqual(
            set(decision.reasons),
            {
                "insufficient_samples",
                "insufficient_events",
                "effect_too_small",
                "multiple_testing_failure",
                "symbol_concentration",
                "time_concentration",
                "parameter_instability",
                "insufficient_effective_sample",
            },
        )

    def test_wrong_hypothesis_evidence_rejected(self):
        frozen = freeze_hypothesis(
            make_spec()
        )

        dataset = DataDeclaration(
            dataset_id="validation-day",
            role=DatasetRole.VALIDATION,
            sealed=False,
        )

        evidence = good_evidence(
            frozen,
            hypothesis_id=(
                "hypothesis:wrong"
            ),
        )

        with self.assertRaises(
            ValueError
        ):
            judge_validation(
                frozen,
                dataset,
                evidence,
            )

    def test_changed_specification_hash_rejected(self):
        frozen = freeze_hypothesis(
            make_spec()
        )

        dataset = DataDeclaration(
            dataset_id="validation-day",
            role=DatasetRole.VALIDATION,
            sealed=False,
        )

        evidence = good_evidence(
            frozen,
            specification_hash=(
                specification_hash(
                    make_spec(
                        horizon=20
                    )
                )
            ),
        )

        with self.assertRaises(
            ValueError
        ):
            judge_validation(
                frozen,
                dataset,
                evidence,
            )

    def test_validation_policy_can_disable_p_value_gate(self):
        frozen = freeze_hypothesis(
            make_spec()
        )

        dataset = DataDeclaration(
            dataset_id="validation-day",
            role=DatasetRole.VALIDATION,
            sealed=False,
        )

        evidence = good_evidence(
            frozen,
            adjusted_p_value=None,
        )

        decision = judge_validation(
            frozen,
            dataset,
            evidence,
            policy=ValidationPolicy(
                max_adjusted_p_value=None
            ),
        )

        self.assertTrue(
            decision.passed
        )

    def test_non_directional_hypothesis_is_allowed(self):
        spec = make_spec(
            scientist="distribution",
            direction=None,
            target=(
                "large_move_probability"
            ),
        )

        frozen = freeze_hypothesis(
            spec
        )

        self.assertIsNone(
            frozen.specification.direction
        )

    def test_tests_considered_is_part_of_identity(self):
        first = make_spec(
            tests_considered=240
        )

        second = make_spec(
            tests_considered=241
        )

        self.assertNotEqual(
            first.hypothesis_id,
            second.hypothesis_id,
        )


if __name__ == "__main__":
    unittest.main()
