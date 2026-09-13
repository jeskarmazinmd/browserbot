import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research_tools.module_factory.feature_matrix import FeatureRow
from research_tools.module_factory.generation_loop import (
    GenerationPolicy,
    run_factory,
)
from research_tools.module_factory.memory import ExperimentMemory
from research_tools.module_factory.search_controller import SearchPolicy


class GenerationLoopTests(unittest.TestCase):
    def _rows(self, day):
        base = datetime(
            2026, 1, day, 14, 30,
            tzinfo=timezone.utc,
        )

        rows = []

        for i in range(160):
            a = float((i % 80) - 40)
            b = float(((i * 7) % 31) - 15)

            # a contains strong repeatable information.
            y = a / 100.0

            rows.append(
                FeatureRow(
                    symbol=f"S{i % 20}",
                    minute=base + timedelta(minutes=i),
                    price=100.0,
                    features={
                        "a": a,
                        "b": b,
                    },
                    forward_returns={
                        1: y,
                        5: y,
                        10: y,
                        20: y,
                    },
                )
            )

        return rows

    def _policy(self):
        return GenerationPolicy(
            generations=1,
            parent_limit=3,
            child_batch_size=5,
            max_children_per_generation=12,
            horizons=(10,),
            min_observations_per_day=100,
            search=SearchPolicy(
                population_limit=4,
                elite_fraction=0.5,
                exploration_fraction=0.25,
                seed=123,
            ),
        )

    def test_generational_run_executes(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = ExperimentMemory(
                Path(folder) / "memory.jsonl"
            )

            run = run_factory(
                {
                    "2026-01-02": self._rows(2),
                    "2026-01-03": self._rows(3),
                },
                memory=memory,
                policy=self._policy(),
            )

            self.assertGreaterEqual(
                len(run.generations),
                1,
            )

            self.assertGreater(
                run.total_tested,
                0,
            )

            self.assertGreater(
                len(memory),
                0,
            )

    def test_second_run_does_not_retest_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = ExperimentMemory(
                Path(folder) / "memory.jsonl"
            )

            rows = {
                "2026-01-02": self._rows(2),
                "2026-01-03": self._rows(3),
            }

            first = run_factory(
                rows,
                memory=memory,
                policy=self._policy(),
            )

            before = len(memory)

            second = run_factory(
                rows,
                memory=memory,
                policy=self._policy(),
            )

            self.assertGreater(
                first.total_tested,
                0,
            )

            self.assertEqual(
                second.generations[0].tested,
                0,
            )

            self.assertEqual(
                len(memory),
                before,
            )

    def test_generated_values_not_added_to_source_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = ExperimentMemory(
                Path(folder) / "memory.jsonl"
            )

            rows = {
                "2026-01-02": self._rows(2),
                "2026-01-03": self._rows(3),
            }

            original_keys = [
                set(row.features)
                for day_rows in rows.values()
                for row in day_rows
            ]

            run_factory(
                rows,
                memory=memory,
                policy=self._policy(),
            )

            after_keys = [
                set(row.features)
                for day_rows in rows.values()
                for row in day_rows
            ]

            self.assertEqual(
                original_keys,
                after_keys,
            )


if __name__ == "__main__":
    unittest.main()
