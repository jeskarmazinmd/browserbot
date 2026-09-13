import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from research_tools.module_factory.dataset_lifecycle import (
    AccessPurpose,
    AuditAction,
    DatasetLifecycleController,
    RegisteredDataset,
    ValidationGrant,
)
from research_tools.module_factory.hypothesis_protocol import (
    DatasetRole,
    freeze_hypothesis,
    make_specification,
)


def make_frozen(
    *,
    lag=5,
    discovery_datasets=(
        "discovery-day",
    ),
):
    spec = make_specification(
        scientist="time_series",
        discovery_id=(
            f"synthetic:lag{lag}"
        ),
        target="forward_return",
        horizon=10,
        features=("signal",),
        parameters={
            "lag": lag,
        },
        direction=1,
        ancestry=(
            "PRICE",
            "TEMPORAL",
        ),
        provenance=(
            "autonomous",
        ),
        discovery_dataset_ids=(
            discovery_datasets
        ),
        multiple_testing_family=(
            "synthetic"
        ),
        tests_considered=20,
        min_samples=100,
        min_events=20,
    )

    return freeze_hypothesis(
        spec
    )


def make_controller():
    controller = (
        DatasetLifecycleController()
    )

    controller.register_many(
        (
            RegisteredDataset(
                dataset_id=(
                    "discovery-day"
                ),
                role=(
                    DatasetRole.DISCOVERY
                ),
                resource_id=(
                    "synthetic://discovery"
                ),
                sealed=False,
            ),
            RegisteredDataset(
                dataset_id=(
                    "validation-day"
                ),
                role=(
                    DatasetRole.VALIDATION
                ),
                resource_id=(
                    "synthetic://validation"
                ),
                sealed=True,
            ),
        )
    )

    return controller


class DatasetLifecycleTests(
    unittest.TestCase
):
    def test_validation_must_register_sealed(self):
        with self.assertRaises(
            ValueError
        ):
            RegisteredDataset(
                dataset_id="validation",
                role=(
                    DatasetRole.VALIDATION
                ),
                resource_id=(
                    "synthetic://validation"
                ),
                sealed=False,
            )

    def test_duplicate_identical_registration_is_idempotent(self):
        controller = (
            DatasetLifecycleController()
        )

        dataset = RegisteredDataset(
            dataset_id="d",
            role=DatasetRole.DISCOVERY,
            resource_id="synthetic://d",
            sealed=False,
        )

        controller.register(
            dataset
        )

        controller.register(
            dataset
        )

        self.assertEqual(
            len(
                controller.audit_log()
            ),
            1,
        )

    def test_conflicting_registration_rejected(self):
        controller = (
            DatasetLifecycleController()
        )

        controller.register(
            RegisteredDataset(
                dataset_id="d",
                role=(
                    DatasetRole.DISCOVERY
                ),
                resource_id="a",
                sealed=False,
            )
        )

        with self.assertRaises(
            ValueError
        ):
            controller.register(
                RegisteredDataset(
                    dataset_id="d",
                    role=(
                        DatasetRole.DISCOVERY
                    ),
                    resource_id="b",
                    sealed=False,
                )
            )

    def test_discovery_access_allowed(self):
        controller = (
            make_controller()
        )

        access = (
            controller.discovery_access(
                "discovery-day"
            )
        )

        self.assertEqual(
            access.purpose,
            AccessPurpose.DISCOVERY,
        )

        self.assertEqual(
            access.resource_id,
            "synthetic://discovery",
        )

    def test_validation_cannot_be_used_for_discovery(self):
        controller = (
            make_controller()
        )

        with self.assertRaises(
            PermissionError
        ):
            controller.discovery_access(
                "validation-day"
            )

    def test_validation_grant_requires_validation_dataset(self):
        controller = (
            make_controller()
        )

        frozen = make_frozen()

        with self.assertRaises(
            PermissionError
        ):
            controller.grant_validation(
                "discovery-day",
                frozen,
            )

    def test_discovery_data_cannot_be_reused_as_validation(self):
        controller = (
            DatasetLifecycleController()
        )

        controller.register(
            RegisteredDataset(
                dataset_id=(
                    "discovery-day"
                ),
                role=(
                    DatasetRole.VALIDATION
                ),
                resource_id=(
                    "synthetic://same"
                ),
                sealed=True,
            )
        )

        frozen = make_frozen(
            discovery_datasets=(
                "discovery-day",
            )
        )

        with self.assertRaises(
            PermissionError
        ):
            controller.grant_validation(
                "discovery-day",
                frozen,
            )

    def test_grant_is_deterministic(self):
        controller = (
            make_controller()
        )

        frozen = make_frozen()

        first = (
            controller.grant_validation(
                "validation-day",
                frozen,
            )
        )

        second = (
            controller.grant_validation(
                "validation-day",
                frozen,
            )
        )

        self.assertEqual(
            first.grant_id,
            second.grant_id,
        )

    def test_grant_is_hypothesis_scoped(self):
        controller = (
            make_controller()
        )

        first_hypothesis = (
            make_frozen(
                lag=5
            )
        )

        second_hypothesis = (
            make_frozen(
                lag=3
            )
        )

        grant = (
            controller.grant_validation(
                "validation-day",
                first_hypothesis,
            )
        )

        with self.assertRaises(
            PermissionError
        ):
            controller.validation_access(
                grant,
                second_hypothesis,
            )

    def test_one_hypothesis_access_does_not_globally_unseal(self):
        controller = (
            make_controller()
        )

        first_hypothesis = (
            make_frozen(
                lag=5
            )
        )

        second_hypothesis = (
            make_frozen(
                lag=3
            )
        )

        first_grant = (
            controller.grant_validation(
                "validation-day",
                first_hypothesis,
            )
        )

        first_access = (
            controller.validation_access(
                first_grant,
                first_hypothesis,
            )
        )

        self.assertEqual(
            first_access.hypothesis_id,
            first_hypothesis.hypothesis_id,
        )

        # The registry itself remains sealed.
        self.assertTrue(
            controller.dataset(
                "validation-day"
            ).sealed
        )

        with self.assertRaises(
            PermissionError
        ):
            controller.validation_access(
                first_grant,
                second_hypothesis,
            )

    def test_second_hypothesis_needs_own_grant(self):
        controller = (
            make_controller()
        )

        first_hypothesis = (
            make_frozen(
                lag=5
            )
        )

        second_hypothesis = (
            make_frozen(
                lag=3
            )
        )

        first_grant = (
            controller.grant_validation(
                "validation-day",
                first_hypothesis,
            )
        )

        second_grant = (
            controller.grant_validation(
                "validation-day",
                second_hypothesis,
            )
        )

        self.assertNotEqual(
            first_grant.grant_id,
            second_grant.grant_id,
        )

        second_access = (
            controller.validation_access(
                second_grant,
                second_hypothesis,
            )
        )

        self.assertEqual(
            second_access.hypothesis_id,
            second_hypothesis.hypothesis_id,
        )

    def test_forged_grant_rejected(self):
        controller = (
            make_controller()
        )

        frozen = make_frozen()

        real = (
            controller.grant_validation(
                "validation-day",
                frozen,
            )
        )

        forged = ValidationGrant(
            grant_id="grant:forged",
            dataset_id=(
                real.dataset_id
            ),
            hypothesis_id=(
                real.hypothesis_id
            ),
            specification_hash=(
                real.specification_hash
            ),
        )

        with self.assertRaises(
            PermissionError
        ):
            controller.validation_access(
                forged,
                frozen,
            )

    def test_modified_grant_rejected(self):
        controller = (
            make_controller()
        )

        frozen = make_frozen()

        real = (
            controller.grant_validation(
                "validation-day",
                frozen,
            )
        )

        modified = replace(
            real,
            specification_hash=(
                "wrong-hash"
            ),
        )

        with self.assertRaises(
            PermissionError
        ):
            controller.validation_access(
                modified,
                frozen,
            )

    def test_unknown_dataset_rejected(self):
        controller = (
            make_controller()
        )

        with self.assertRaises(
            KeyError
        ):
            controller.discovery_access(
                "missing"
            )

    def test_audit_log_records_successful_lifecycle(self):
        controller = (
            make_controller()
        )

        frozen = make_frozen()

        controller.discovery_access(
            "discovery-day"
        )

        grant = (
            controller.grant_validation(
                "validation-day",
                frozen,
            )
        )

        controller.validation_access(
            grant,
            frozen,
        )

        actions = [
            event.action
            for event
            in controller.audit_log()
        ]

        self.assertIn(
            AuditAction.REGISTER,
            actions,
        )

        self.assertIn(
            AuditAction.DISCOVERY_ACCESS,
            actions,
        )

        self.assertIn(
            AuditAction.VALIDATION_GRANT,
            actions,
        )

        self.assertIn(
            AuditAction.VALIDATION_ACCESS,
            actions,
        )

    def test_denial_is_audited(self):
        controller = (
            make_controller()
        )

        with self.assertRaises(
            PermissionError
        ):
            controller.discovery_access(
                "validation-day"
            )

        self.assertEqual(
            controller.audit_log()[
                -1
            ].action,
            AuditAction.ACCESS_DENIED,
        )


if __name__ == "__main__":
    unittest.main()


class ValidationBatchLifecycleTests(unittest.TestCase):
    """
    Validation datasets are one-shot scientific resources.

    Every hypothesis in a validation batch must be frozen before the
    batch is sealed. Once validation begins, membership is immutable.
    Once the batch is finalized, the dataset is SPENT and can never be
    granted to a later batch.
    """

    def test_batch_membership_is_frozen_before_validation(self):
        controller = make_controller()
        first = make_frozen(lag=5)
        second = make_frozen(lag=3)

        batch = controller.create_validation_batch(
            "validation-day",
            (first, second),
        )

        self.assertEqual(
            set(batch.hypothesis_ids),
            {
                first.hypothesis_id,
                second.hypothesis_id,
            },
        )

        grants = controller.grant_validation_batch(
            batch.batch_id,
            (first, second),
        )

        self.assertEqual(len(grants), 2)

    def test_batch_rejects_hypothesis_added_after_seal(self):
        controller = make_controller()
        first = make_frozen(lag=5)
        later = make_frozen(lag=3)

        batch = controller.create_validation_batch(
            "validation-day",
            (first,),
        )

        with self.assertRaises(PermissionError):
            controller.grant_validation_batch(
                batch.batch_id,
                (first, later),
            )

    def test_validation_access_requires_batch_membership(self):
        controller = make_controller()
        first = make_frozen(lag=5)
        outsider = make_frozen(lag=3)

        batch = controller.create_validation_batch(
            "validation-day",
            (first,),
        )

        grants = controller.grant_validation_batch(
            batch.batch_id,
            (first,),
        )

        controller.validation_batch_access(
            batch.batch_id,
            grants[0],
            first,
        )

        outsider_grant = controller.grant_validation(
            "validation-day",
            outsider,
        )

        with self.assertRaises(PermissionError):
            controller.validation_batch_access(
                batch.batch_id,
                outsider_grant,
                outsider,
            )

    def test_dataset_becomes_spent_after_batch_finalization(self):
        controller = make_controller()
        first = make_frozen(lag=5)

        batch = controller.create_validation_batch(
            "validation-day",
            (first,),
        )

        grants = controller.grant_validation_batch(
            batch.batch_id,
            (first,),
        )

        controller.validation_batch_access(
            batch.batch_id,
            grants[0],
            first,
        )

        controller.finalize_validation_batch(
            batch.batch_id,
        )

        self.assertTrue(
            controller.validation_dataset_spent(
                "validation-day"
            )
        )

    def test_spent_dataset_cannot_validate_later_batch(self):
        controller = make_controller()
        first = make_frozen(lag=5)
        later = make_frozen(lag=3)

        first_batch = controller.create_validation_batch(
            "validation-day",
            (first,),
        )

        grants = controller.grant_validation_batch(
            first_batch.batch_id,
            (first,),
        )

        controller.validation_batch_access(
            first_batch.batch_id,
            grants[0],
            first,
        )

        controller.finalize_validation_batch(
            first_batch.batch_id,
        )

        with self.assertRaises(PermissionError):
            controller.create_validation_batch(
                "validation-day",
                (later,),
            )

        with self.assertRaises(PermissionError):
            controller.grant_validation(
                "validation-day",
                later,
            )

    def test_batch_identity_is_deterministic_and_order_independent(self):
        first = make_frozen(lag=5)
        second = make_frozen(lag=3)

        a = make_controller().create_validation_batch(
            "validation-day",
            (first, second),
        )

        b = make_controller().create_validation_batch(
            "validation-day",
            (second, first),
        )

        self.assertEqual(a.batch_id, b.batch_id)
        self.assertEqual(
            a.manifest_hash,
            b.manifest_hash,
        )



class ValidationBatchDurabilityTests(unittest.TestCase):
    def make_persistent_controller(self, state_path):
        controller = DatasetLifecycleController(
            state_path=state_path,
        )

        controller.register_many(
            (
                RegisteredDataset(
                    dataset_id="discovery-day",
                    role=DatasetRole.DISCOVERY,
                    resource_id="synthetic://discovery",
                    sealed=False,
                ),
                RegisteredDataset(
                    dataset_id="validation-day",
                    role=DatasetRole.VALIDATION,
                    resource_id="synthetic://validation",
                    sealed=True,
                ),
            )
        )

        return controller

    def test_spent_state_survives_controller_restart(self):
        with tempfile.TemporaryDirectory() as root:
            state_path = (
                Path(root) / "dataset_lifecycle.json"
            )

            controller = (
                self.make_persistent_controller(
                    state_path
                )
            )

            frozen = make_frozen()

            batch = controller.create_validation_batch(
                "validation-day",
                (frozen,),
            )

            grant = (
                controller.grant_validation_batch(
                    batch.batch_id,
                    (frozen,),
                )[0]
            )

            controller.validation_batch_access(
                batch.batch_id,
                grant,
                frozen,
            )

            controller.finalize_validation_batch(
                batch.batch_id
            )

            self.assertTrue(
                controller.validation_dataset_spent(
                    "validation-day"
                )
            )

            restarted = (
                self.make_persistent_controller(
                    state_path
                )
            )

            self.assertTrue(
                restarted.validation_dataset_spent(
                    "validation-day"
                )
            )

            later = make_frozen(lag=3)

            with self.assertRaises(PermissionError):
                restarted.create_validation_batch(
                    "validation-day",
                    (later,),
                )

            with self.assertRaises(PermissionError):
                restarted.grant_validation(
                    "validation-day",
                    later,
                )

    def test_sealed_batch_survives_controller_restart(self):
        with tempfile.TemporaryDirectory() as root:
            state_path = (
                Path(root) / "dataset_lifecycle.json"
            )

            controller = (
                self.make_persistent_controller(
                    state_path
                )
            )

            first = make_frozen(lag=5)
            second = make_frozen(lag=3)

            batch = controller.create_validation_batch(
                "validation-day",
                (first, second),
            )

            restarted = (
                self.make_persistent_controller(
                    state_path
                )
            )

            restored = restarted.validation_batch(
                batch.batch_id
            )

            self.assertEqual(
                restored.manifest_hash,
                batch.manifest_hash,
            )

            self.assertEqual(
                restored.hypothesis_ids,
                batch.hypothesis_ids,
            )

            outsider = make_frozen(lag=8)

            with self.assertRaises(PermissionError):
                restarted.grant_validation_batch(
                    batch.batch_id,
                    (first, outsider),
                )

    def test_batch_cannot_finalize_before_all_members_accessed(self):
        controller = make_controller()

        first = make_frozen(lag=5)
        second = make_frozen(lag=3)

        batch = controller.create_validation_batch(
            "validation-day",
            (first, second),
        )

        grants = controller.grant_validation_batch(
            batch.batch_id,
            (first, second),
        )

        controller.validation_batch_access(
            batch.batch_id,
            grants[0],
            first,
        )

        with self.assertRaises(PermissionError):
            controller.finalize_validation_batch(
                batch.batch_id
            )

        controller.validation_batch_access(
            batch.batch_id,
            grants[1],
            second,
        )

        finalized = (
            controller.finalize_validation_batch(
                batch.batch_id
            )
        )

        self.assertTrue(finalized.finalized)
        self.assertTrue(
            controller.validation_dataset_spent(
                "validation-day"
            )
        )


class ValidationBatchSupersessionTests(unittest.TestCase):

    def _controller(self, state_path=None):
        controller = DatasetLifecycleController(
            state_path=state_path
        )
        controller.register(
            RegisteredDataset(
                dataset_id="validation:test",
                resource_id="/tmp/validation-test.csv",
                role=DatasetRole.VALIDATION,
                sealed=True,
            )
        )
        return controller

    def _frozen(self, name, tests=10):
        spec = make_specification(
            scientist="test",
            discovery_id=name,
            target="forward_return",
            horizon=5,
            features=(name,),
            parameters={},
            direction=1,
            ancestry=("PRICE",),
            provenance=("test",),
            discovery_dataset_ids=(
                "discovery:test",
            ),
            multiple_testing_family="test",
            tests_considered=tests,
            min_samples=30,
            min_events=1,
        )
        return freeze_hypothesis(spec)

    def test_untouched_batch_can_be_superseded(self):
        controller = self._controller()

        first = (
            self._frozen("first")
        )

        batch = controller.create_validation_batch(
            "validation:test",
            (first,),
        )

        retired = (
            controller.supersede_validation_batch(
                batch.batch_id
            )
        )

        self.assertEqual(
            retired.batch_id,
            batch.batch_id,
        )

        with self.assertRaises(KeyError):
            controller.validation_batch(
                batch.batch_id
            )

        second = self._frozen(
            "first",
            tests=20,
        )

        replacement = (
            controller.create_validation_batch(
                "validation:test",
                (second,),
            )
        )

        self.assertNotEqual(
            replacement.batch_id,
            batch.batch_id,
        )

        self.assertFalse(
            controller.validation_dataset_spent(
                "validation:test"
            )
        )

    def test_supersession_revokes_unused_grant(self):
        controller = self._controller()

        frozen = self._frozen("first")

        batch = controller.create_validation_batch(
            "validation:test",
            (frozen,),
        )

        grant = (
            controller.grant_validation_batch(
                batch.batch_id,
                (frozen,),
            )[0]
        )

        controller.supersede_validation_batch(
            batch.batch_id
        )

        with self.assertRaises(
            PermissionError
        ):
            controller.validation_access(
                grant,
                frozen,
            )

    def test_accessed_batch_cannot_be_superseded(self):
        controller = self._controller()

        frozen = self._frozen("first")

        batch = controller.create_validation_batch(
            "validation:test",
            (frozen,),
        )

        grant = (
            controller.grant_validation_batch(
                batch.batch_id,
                (frozen,),
            )[0]
        )

        controller.validation_batch_access(
            batch.batch_id,
            grant,
            frozen,
        )

        with self.assertRaises(
            PermissionError
        ):
            controller.supersede_validation_batch(
                batch.batch_id
            )

    def test_superseded_tombstone_survives_restart(self):
        import json
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            state = (
                Path(tmp)
                / "lifecycle.json"
            )

            controller = self._controller(
                state
            )

            frozen = self._frozen("first")

            batch = (
                controller.create_validation_batch(
                    "validation:test",
                    (frozen,),
                )
            )

            controller.supersede_validation_batch(
                batch.batch_id
            )

            payload = json.loads(
                state.read_text()
            )

            ids = {
                item["batch_id"]
                for item
                in payload[
                    "superseded_validation_batches"
                ]
            }

            self.assertIn(
                batch.batch_id,
                ids,
            )

            restarted = self._controller(
                state
            )

            self.assertIn(
                batch.batch_id,
                restarted
                    ._superseded_validation_batches,
            )

            self.assertFalse(
                restarted.validation_dataset_spent(
                    "validation:test"
                )
            )
