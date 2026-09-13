import json
import tempfile
import unittest
from pathlib import Path

from research_tools.module_factory.dataset_lifecycle import (
    DatasetLifecycleController,
    RegisteredDataset,
)
from research_tools.module_factory.hypothesis_protocol import (
    DatasetRole,
    freeze_hypothesis,
    make_specification,
)
from research_tools.module_factory.validation_execution import (
    execute_sealed_batch,
)


class ValidationExecutionTests(unittest.TestCase):

    def _frozen(self, name):
        return freeze_hypothesis(
            make_specification(
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
                tests_considered=10,
                min_samples=1,
                min_events=1,
            )
        )

    def _setup(self, tmp):
        state = Path(tmp) / "state.json"
        resource = (
            Path(tmp) / "validation.csv"
        )
        resource.write_text("sealed\n")

        controller = (
            DatasetLifecycleController(
                state_path=state
            )
        )

        controller.register(
            RegisteredDataset(
                dataset_id="validation:test",
                resource_id=str(resource),
                role=DatasetRole.VALIDATION,
                sealed=True,
            )
        )

        frozen = (
            self._frozen("a"),
            self._frozen("b"),
        )

        batch = (
            controller.create_validation_batch(
                "validation:test",
                frozen,
            )
        )

        return (
            controller,
            frozen,
            batch,
            state,
        )

    def test_success_loads_once_and_spends(self):
        with tempfile.TemporaryDirectory() as tmp:
            (
                controller,
                frozen,
                batch,
                state,
            ) = self._setup(tmp)

            calls = []

            def load_rows(resource_id):
                calls.append(resource_id)
                return ("row",)

            def validate(hypothesis, rows):
                self.assertEqual(
                    rows,
                    ("row",),
                )
                return {
                    "effect": 1.0,
                    "id":
                        hypothesis.hypothesis_id,
                }

            report_path = (
                Path(tmp) / "report.json"
            )

            report, finalized = (
                execute_sealed_batch(
                    controller=controller,
                    batch=batch,
                    frozen=frozen,
                    load_rows=load_rows,
                    validate=validate,
                    report_path=report_path,
                )
            )

            self.assertEqual(
                len(calls),
                1,
            )

            self.assertEqual(
                len(report["results"]),
                2,
            )

            self.assertTrue(
                finalized.finalized
            )

            self.assertTrue(
                controller.validation_dataset_spent(
                    "validation:test"
                )
            )

            persisted = json.loads(
                report_path.read_text()
            )

            self.assertTrue(
                persisted["complete"]
            )
            self.assertTrue(
                persisted["finalized"]
            )
            self.assertTrue(
                persisted["dataset_spent"]
            )

            restarted = (
                DatasetLifecycleController(
                    state_path=state
                )
            )

            restarted.register(
                RegisteredDataset(
                    dataset_id="validation:test",
                    resource_id=controller.dataset(
                        "validation:test"
                    ).resource_id,
                    role=DatasetRole.VALIDATION,
                    sealed=True,
                )
            )

            self.assertTrue(
                restarted.validation_dataset_spent(
                    "validation:test"
                )
            )

    def test_validation_failure_does_not_finalize(self):
        with tempfile.TemporaryDirectory() as tmp:
            (
                controller,
                frozen,
                batch,
                _,
            ) = self._setup(tmp)

            def validate(hypothesis, rows):
                raise RuntimeError(
                    "synthetic evaluation failure"
                )

            with self.assertRaises(
                RuntimeError
            ):
                execute_sealed_batch(
                    controller=controller,
                    batch=batch,
                    frozen=frozen,
                    load_rows=lambda _: ("row",),
                    validate=validate,
                    report_path=(
                        Path(tmp) / "report.json"
                    ),
                )

            self.assertFalse(
                controller.validation_batch(
                    batch.batch_id
                ).finalized
            )

            self.assertFalse(
                controller.validation_dataset_spent(
                    "validation:test"
                )
            )

            # But access is durably recorded, so the
            # failed run cannot be superseded as pristine.
            with self.assertRaises(
                PermissionError
            ):
                controller.supersede_validation_batch(
                    batch.batch_id
                )

    def test_report_failure_does_not_finalize(self):
        with tempfile.TemporaryDirectory() as tmp:
            (
                controller,
                frozen,
                batch,
                _,
            ) = self._setup(tmp)

            bad_report = (
                Path(tmp)
                / "missing"
                / "report.json"
            )

            with self.assertRaises(
                FileNotFoundError
            ):
                execute_sealed_batch(
                    controller=controller,
                    batch=batch,
                    frozen=frozen,
                    load_rows=lambda _: ("row",),
                    validate=lambda *_: {
                        "effect": 1.0
                    },
                    report_path=bad_report,
                )

            self.assertFalse(
                controller.validation_batch(
                    batch.batch_id
                ).finalized
            )

            self.assertFalse(
                controller.validation_dataset_spent(
                    "validation:test"
                )
            )


if __name__ == "__main__":
    unittest.main()
