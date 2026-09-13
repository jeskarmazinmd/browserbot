import json
import tempfile
import unittest
from pathlib import Path

from research_tools.module_factory.memory import (
    ExperimentMemory,
    experiment_id,
    record_candidate_result,
)


class MemoryTests(unittest.TestCase):
    def test_experiment_ids_are_deterministic(self):
        self.assertEqual(
            experiment_id("return_5", 10),
            experiment_id("return_5", 10),
        )

        self.assertNotEqual(
            experiment_id("return_5", 10),
            experiment_id("return_5", 20),
        )

    def test_create_and_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "memory.jsonl"

            memory = ExperimentMemory(path)

            record = memory.create(
                feature="return_5",
                horizon=10,
                generation=0,
                lineage=("return_5",),
            )

            self.assertTrue(
                memory.seen("return_5", 10)
            )

            reloaded = ExperimentMemory(path)

            self.assertEqual(len(reloaded), 1)
            self.assertEqual(
                reloaded.get(
                    "return_5",
                    10,
                ).experiment_id,
                record.experiment_id,
            )

    def test_create_does_not_duplicate_existing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "memory.jsonl"
            memory = ExperimentMemory(path)

            first = memory.create(
                feature="x",
                horizon=20,
                generation=0,
                lineage=("x",),
            )

            second = memory.create(
                feature="x",
                horizon=20,
                generation=0,
                lineage=("x",),
            )

            self.assertEqual(
                first.experiment_id,
                second.experiment_id,
            )

            lines = path.read_text().splitlines()

            self.assertEqual(len(lines), 1)

    def test_updates_are_append_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "memory.jsonl"
            memory = ExperimentMemory(path)

            record = memory.create(
                feature="x",
                horizon=10,
                generation=0,
                lineage=("x",),
            )

            memory.update(
                record,
                status="TESTED",
                test_count=1,
            )

            lines = path.read_text().splitlines()

            self.assertEqual(len(lines), 2)

            reloaded = ExperimentMemory(path)
            current = reloaded.get("x", 10)

            self.assertEqual(
                current.status,
                "TESTED",
            )

            self.assertEqual(
                current.test_count,
                1,
            )

    def test_failed_ideas_remain_known(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = ExperimentMemory(
                Path(folder) / "memory.jsonl"
            )

            record_candidate_result(
                memory,
                feature="bad_math",
                horizon=10,
                generation=1,
                lineage=("bad_math", "a", "b"),
                discovery_score=-1.0,
                search_score=-1.0,
                bh_pass=False,
                sign_consistency=0.0,
                worst_day_edge=-0.5,
                observations=1000,
                selected=False,
                rejection_reason="poor_day_consistency",
            )

            current = memory.get(
                "bad_math",
                10,
            )

            self.assertEqual(
                current.status,
                "HISTORICAL_REJECT",
            )

            self.assertTrue(
                memory.seen(
                    "bad_math",
                    10,
                )
            )

    def test_untested_filters_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = ExperimentMemory(
                Path(folder) / "memory.jsonl"
            )

            memory.create(
                feature="known",
                horizon=10,
                generation=0,
                lineage=("known",),
            )

            result = memory.untested(
                [
                    ("known", 10),
                    ("new", 10),
                    ("known", 20),
                ]
            )

            self.assertEqual(
                result,
                [
                    ("new", 10),
                    ("known", 20),
                ],
            )


if __name__ == "__main__":
    unittest.main()
