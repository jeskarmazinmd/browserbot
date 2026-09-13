import json
import tempfile
import unittest
from pathlib import Path

from research_tools.module_factory.real_validation_batch_runner import (
    _parameters,
    reconstruct_frozen,
)


class RealValidationBatchRunnerTests(
    unittest.TestCase
):

    def test_parameter_pairs_reconstruct(self):
        self.assertEqual(
            _parameters([
                ["lag", 3],
                ["threshold", 1.25],
            ]),
            {
                "lag": 3,
                "threshold": 1.25,
            },
        )

    def test_manifest_frozen_identity_round_trip(self):
        manifest = json.loads(
            Path(
                "research_data/"
                "factory_validation_batch_001.json"
            ).read_text()
        )

        reconstructed = [
            reconstruct_frozen(item)
            for item in manifest["hypotheses"]
        ]

        self.assertEqual(
            len(reconstructed),
            5,
        )

        self.assertEqual(
            {
                item.hypothesis_id
                for item in reconstructed
            },
            {
                item["hypothesis_id"]
                for item in manifest["hypotheses"]
            },
        )

        self.assertEqual(
            {
                item.specification_hash
                for item in reconstructed
            },
            {
                item["specification_hash"]
                for item in manifest["hypotheses"]
            },
        )

    def test_changed_specification_is_rejected(self):
        manifest = json.loads(
            Path(
                "research_data/"
                "factory_validation_batch_001.json"
            ).read_text()
        )

        item = json.loads(
            json.dumps(
                manifest["hypotheses"][0]
            )
        )

        item["specification"]["horizon"] += 1

        with self.assertRaises(
            RuntimeError
        ):
            reconstruct_frozen(item)


if __name__ == "__main__":
    unittest.main()
