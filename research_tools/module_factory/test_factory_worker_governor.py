import json
from pathlib import Path
import tempfile
import unittest

from research_tools.module_factory.factory_shadow_worker import (
    FactoryShadowWorker,
)
from research_tools.module_factory.module_registry import (
    FactoryModuleRegistry,
    ModuleState,
)
from research_tools.module_factory.resource_governor import (
    ResourceDecision,
    ResourceSnapshot,
)


class FakeGovernor:
    def __init__(self, allowed):
        self.allowed = allowed
        self.calls = 0

    def check(self, *, data_root):
        self.calls += 1

        return ResourceDecision(
            allowed=self.allowed,
            reasons=(
                ()
                if self.allowed
                else ("memory_available_below_floor",)
            ),
            snapshot=ResourceSnapshot(
                memory_available_mb=(
                    1600 if self.allowed else 100
                ),
                memory_total_mb=4096,
                load_1m=1,
                cpu_count=8,
                data_free_mb=2000,
            ),
        )


class FactoryWorkerGovernorTests(unittest.TestCase):
    def setup_worker(self, root, governor):
        root = Path(root)

        tape = root / "quotes.csv"
        tape.write_text(
            "timestamp_utc,symbol,last_price\n"
        )

        registry_path = root / "registry.json"
        spec_path = root / "specs.json"

        registry = FactoryModuleRegistry(
            registry_path,
            max_shadow_modules=2,
        )

        registry.register_candidate(
            module_id="FM_A",
            hypothesis_id="hypothesis:A",
            specification_hash="hash-A",
            scientist="test",
            score=1.0,
        )
        registry.transition(
            "FM_A",
            ModuleState.HISTORICAL_PASS,
        )
        registry.transition(
            "FM_A",
            ModuleState.SHADOW,
        )

        spec_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "strategies": [
                        {
                            "module_id": "FM_A",
                            "hypothesis_id":
                                "hypothesis:A",
                            "specification_hash":
                                "hash-A",
                            "scientist": "test",
                            "feature": "return_30",
                            "horizon": 20,
                            "direction": 1,
                            "threshold": 0,
                        }
                    ],
                }
            )
        )

        worker = FactoryShadowWorker(
            tape_path=tape,
            registry_path=registry_path,
            spec_path=spec_path,
            state_path=root / "state.json",
            signal_path=root / "signals.jsonl",
            max_shadow_modules=2,
            max_minutes_per_cycle=100,
            history_minutes=75,
            start_at_end=False,
            resource_governor=governor,
            resource_data_root=root,
            healthy_checks_to_resume=1,
        )

        return worker, tape

    def test_denied_resources_do_not_advance_tape(self):
        with tempfile.TemporaryDirectory() as root:
            governor = FakeGovernor(False)
            worker, tape = self.setup_worker(
                root,
                governor,
            )

            try:
                with tape.open("a") as handle:
                    handle.write(
                        "2026-09-03T14:00:01+00:00,"
                        "AAA,100\n"
                        "2026-09-03T14:01:01+00:00,"
                        "AAA,101\n"
                    )

                before = worker.feed.offset
                result = worker.cycle()

                self.assertFalse(
                    result.resource_allowed
                )
                self.assertEqual(
                    result.completed_minutes,
                    0,
                )
                self.assertEqual(
                    result.feature_rows,
                    0,
                )
                self.assertEqual(
                    result.signals,
                    0,
                )
                self.assertEqual(
                    worker.feed.offset,
                    before,
                )
            finally:
                worker.close()

    def test_worker_resumes_after_resources_recover(self):
        with tempfile.TemporaryDirectory() as root:
            governor = FakeGovernor(False)
            worker, tape = self.setup_worker(
                root,
                governor,
            )

            try:
                with tape.open("a") as handle:
                    handle.write(
                        "2026-09-03T14:00:01+00:00,"
                        "AAA,100\n"
                        "2026-09-03T14:01:01+00:00,"
                        "AAA,101\n"
                    )

                denied = worker.cycle()

                self.assertFalse(
                    denied.resource_allowed
                )

                governor.allowed = True

                allowed = worker.cycle()

                self.assertTrue(
                    allowed.resource_allowed
                )
                self.assertEqual(
                    allowed.completed_minutes,
                    1,
                )
            finally:
                worker.close()


if __name__ == "__main__":
    unittest.main()
