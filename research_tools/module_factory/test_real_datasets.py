import tempfile
import unittest
from pathlib import Path

from research_tools.module_factory.hypothesis_protocol import (
    DatasetRole,
)
from research_tools.module_factory.real_datasets import (
    AUG28_DATASET_ID,
    AUG28_RELATIVE_PATH,
    SEP02_DATASET_ID,
    SEP02_RELATIVE_PATH,
    build_real_dataset_controller,
    dataset_declarations,
    verify_real_dataset_metadata,
)


class RealDatasetDeclarationTests(
    unittest.TestCase
):
    def test_aug28_is_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            aug28, _ = (
                dataset_declarations(
                    tmp
                )
            )

            self.assertEqual(
                aug28.dataset_id,
                AUG28_DATASET_ID,
            )

            self.assertEqual(
                aug28.role,
                DatasetRole.DISCOVERY,
            )

            self.assertFalse(
                aug28.sealed
            )

    def test_sep02_is_validation_and_sealed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, sep02 = (
                dataset_declarations(
                    tmp
                )
            )

            self.assertEqual(
                sep02.dataset_id,
                SEP02_DATASET_ID,
            )

            self.assertEqual(
                sep02.role,
                DatasetRole.VALIDATION,
            )

            self.assertTrue(
                sep02.sealed
            )

    def test_paths_resolve_under_repo_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(
                tmp
            ).resolve()

            aug28, sep02 = (
                dataset_declarations(
                    root
                )
            )

            self.assertEqual(
                Path(
                    aug28.resource_id
                ),
                root
                / AUG28_RELATIVE_PATH,
            )

            self.assertEqual(
                Path(
                    sep02.resource_id
                ),
                root
                / SEP02_RELATIVE_PATH,
            )

    def test_controller_keeps_sep02_sealed(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = (
                build_real_dataset_controller(
                    tmp
                )
            )

            self.assertFalse(
                controller.dataset(
                    AUG28_DATASET_ID
                ).sealed
            )

            self.assertTrue(
                controller.dataset(
                    SEP02_DATASET_ID
                ).sealed
            )

    def test_discovery_access_to_sep02_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = (
                build_real_dataset_controller(
                    tmp
                )
            )

            with self.assertRaises(
                PermissionError
            ):
                controller.discovery_access(
                    SEP02_DATASET_ID
                )

    def test_metadata_check_does_not_require_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(
                tmp
            )

            aug_path = (
                root
                / AUG28_RELATIVE_PATH
            )

            sep_path = (
                root
                / SEP02_RELATIVE_PATH
            )

            aug_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            sep_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            aug_path.touch()
            sep_path.touch()

            metadata = (
                verify_real_dataset_metadata(
                    root
                )
            )

            self.assertEqual(
                len(metadata),
                2,
            )

            self.assertTrue(
                all(
                    item["exists"]
                    for item
                    in metadata
                )
            )

            self.assertTrue(
                all(
                    item["is_file"]
                    for item
                    in metadata
                )
            )

            self.assertTrue(
                metadata[1][
                    "sealed"
                ]
            )


if __name__ == "__main__":
    unittest.main()
