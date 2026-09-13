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


class FactoryShadowWorkerTests(unittest.TestCase):
    def setup_worker(
        self,
        root,
        *,
        max_minutes=5,
    ):
        root = Path(root)

        tape = root / "quotes.csv"
        tape.write_text(
            "timestamp_utc,symbol,last_price\n"
        )

        registry_path = root / "registry.json"
        spec_path = root / "specs.json"
        state_path = root / "state.json"
        signal_path = root / "signals.jsonl"

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
                            "threshold": 0.0,
                        }
                    ],
                }
            )
        )

        worker = FactoryShadowWorker(
            tape_path=tape,
            registry_path=registry_path,
            spec_path=spec_path,
            state_path=state_path,
            signal_path=signal_path,
            max_shadow_modules=2,
            max_signals_per_cycle=100,
            max_minutes_per_cycle=max_minutes,
            history_minutes=75,
            start_at_end=False,
        )

        return (
            worker,
            tape,
            signal_path,
        )

    @staticmethod
    def append_minute(
        tape,
        minute,
        aaa,
        spy,
    ):
        with tape.open("a") as handle:
            handle.write(
                "2026-09-03T"
                f"14:{minute:02d}:01+00:00,"
                f"AAA,{aaa}\n"
            )
            handle.write(
                "2026-09-03T"
                f"14:{minute:02d}:02+00:00,"
                f"SPY,{spy}\n"
            )

    def test_pipeline_reaches_shadow_runtime(self):
        with tempfile.TemporaryDirectory() as root:
            worker, tape, signals = (
                self.setup_worker(root)
            )

            try:
                # 14:00 through 14:59.
                for minute in range(60):
                    self.append_minute(
                        tape,
                        minute,
                        100 + minute,
                        500 + minute * 0.1,
                    )

                first = worker.cycle()

                # Bounded catch-up means only five completed
                # minutes are consumed this cycle.
                self.assertEqual(
                    first.completed_minutes,
                    5,
                )

                # Feed again with a clean synthetic hour so the
                # feature engine obtains 61 contiguous minutes.
                #
                # We use a fresh worker below for clarity.
            finally:
                worker.close()

    def test_end_to_end_signal_after_warmup(self):
        with tempfile.TemporaryDirectory() as root:
            worker, tape, signals = (
                self.setup_worker(
                    root,
                    max_minutes=100,
                )
            )

            try:
                # Produce 61 completed minutes plus one open
                # minute to release minute 60.
                for index in range(62):
                    hour = 14 + index // 60
                    minute = index % 60

                    with tape.open("a") as handle:
                        handle.write(
                            "2026-09-03T"
                            f"{hour:02d}:{minute:02d}:01"
                            "+00:00,"
                            f"AAA,{100 + index}\n"
                        )
                        handle.write(
                            "2026-09-03T"
                            f"{hour:02d}:{minute:02d}:02"
                            "+00:00,"
                            f"SPY,{500 + index * 0.1}\n"
                        )

                result = worker.cycle()

                self.assertEqual(
                    result.completed_minutes,
                    61,
                )

                self.assertGreater(
                    result.feature_rows,
                    0,
                )

                self.assertGreater(
                    result.signals,
                    0,
                )

                self.assertTrue(
                    signals.exists()
                )

                payloads = [
                    json.loads(line)
                    for line
                    in signals.read_text().splitlines()
                    if line.strip()
                ]

                self.assertTrue(payloads)

                self.assertTrue(
                    all(
                        item["data"]["paper_only"]
                        for item in payloads
                    )
                )

                self.assertTrue(
                    all(
                        item["data"][
                            "live_order_placement"
                        ] is False
                        for item in payloads
                    )
                )
            finally:
                worker.close()

    def test_no_signal_before_feature_warmup(self):
        with tempfile.TemporaryDirectory() as root:
            worker, tape, signals = (
                self.setup_worker(
                    root,
                    max_minutes=100,
                )
            )

            try:
                for minute in range(20):
                    self.append_minute(
                        tape,
                        minute,
                        100 + minute,
                        500 + minute,
                    )

                # Release minute 19.
                self.append_minute(
                    tape,
                    20,
                    120,
                    520,
                )

                result = worker.cycle()

                self.assertEqual(
                    result.feature_rows,
                    0,
                )
                self.assertEqual(
                    result.signals,
                    0,
                )
                self.assertFalse(
                    signals.exists()
                )
            finally:
                worker.close()

    def test_cycle_minute_limit_is_hard(self):
        with tempfile.TemporaryDirectory() as root:
            worker, tape, _ = (
                self.setup_worker(
                    root,
                    max_minutes=3,
                )
            )

            try:
                for minute in range(10):
                    self.append_minute(
                        tape,
                        minute,
                        100 + minute,
                        500 + minute,
                    )

                result = worker.cycle()

                self.assertEqual(
                    result.completed_minutes,
                    3,
                )
            finally:
                worker.close()


if __name__ == "__main__":
    unittest.main()
