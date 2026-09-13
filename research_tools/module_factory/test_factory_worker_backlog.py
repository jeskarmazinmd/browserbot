import json
from pathlib import Path
import tempfile
import unittest

from research_tools.module_factory.factory_shadow_worker import (
    FactoryShadowWorker,
)
from research_tools.module_factory.module_registry import (
    FactoryModuleRegistry,
)


class FactoryWorkerBacklogTests(unittest.TestCase):
    def make_worker(self, root):
        root = Path(root)

        tape = root / "quotes.csv"
        tape.write_text(
            "timestamp_utc,symbol,last_price\n"
        )

        registry_path = root / "registry.json"
        spec_path = root / "specs.json"

        FactoryModuleRegistry(
            registry_path,
            max_shadow_modules=2,
        )

        spec_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "strategies": [],
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
            max_minutes_per_cycle=3,
            history_minutes=75,
            start_at_end=False,
            resource_governor=None,
            resource_data_root=root,
        )

        return worker, tape

    def test_backlog_is_deferred_not_dropped(self):
        with tempfile.TemporaryDirectory() as root:
            worker, tape = self.make_worker(root)

            try:
                with tape.open("a") as handle:
                    # 11 clock minutes create 10 completed
                    # minutes; newest minute is withheld.
                    for minute in range(11):
                        handle.write(
                            "2026-09-03T14:"
                            f"{minute:02d}:01+00:00,"
                            f"AAA,{100 + minute}\n"
                        )

                results = [
                    worker.cycle(),
                    worker.cycle(),
                    worker.cycle(),
                    worker.cycle(),
                ]

                counts = [
                    result.completed_minutes
                    for result in results
                ]

                self.assertEqual(
                    counts,
                    [3, 3, 3, 1],
                )

                self.assertEqual(
                    len(worker._pending_minutes),
                    0,
                )

            finally:
                worker.close()

    def test_pending_backlog_is_drained_before_new_poll(self):
        with tempfile.TemporaryDirectory() as root:
            worker, tape = self.make_worker(root)

            try:
                with tape.open("a") as handle:
                    for minute in range(6):
                        handle.write(
                            "2026-09-03T14:"
                            f"{minute:02d}:01+00:00,"
                            f"AAA,{100 + minute}\n"
                        )

                first = worker.cycle()

                self.assertEqual(
                    first.completed_minutes,
                    3,
                )

                self.assertEqual(
                    len(worker._pending_minutes),
                    2,
                )

                offset_after_first = worker.feed.offset

                second = worker.cycle()

                self.assertEqual(
                    second.completed_minutes,
                    2,
                )

                # No second tape poll was needed while
                # deferred minutes were still pending.
                self.assertEqual(
                    worker.feed.offset,
                    offset_after_first,
                )

            finally:
                worker.close()


if __name__ == "__main__":
    unittest.main()


class FactoryWorkerRestartBacklogTests(unittest.TestCase):
    def make_worker(self, root):
        root = Path(root)

        tape = root / "quotes.csv"
        if not tape.exists():
            tape.write_text(
                "timestamp_utc,symbol,last_price\n"
            )

        registry_path = root / "registry.json"
        spec_path = root / "specs.json"

        if not registry_path.exists():
            FactoryModuleRegistry(
                registry_path,
                max_shadow_modules=2,
            )

        if not spec_path.exists():
            spec_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "strategies": [],
                    }
                )
            )

        return FactoryShadowWorker(
            tape_path=tape,
            registry_path=registry_path,
            spec_path=spec_path,
            state_path=root / "state.json",
            signal_path=root / "signals.jsonl",
            max_shadow_modules=2,
            max_minutes_per_cycle=3,
            history_minutes=75,
            start_at_end=False,
            resource_governor=None,
            resource_data_root=root,
        ), tape

    def test_restart_does_not_lose_unprocessed_backlog(self):
        with tempfile.TemporaryDirectory() as root:
            worker, tape = self.make_worker(root)

            with tape.open("a") as handle:
                # 11 observed clock minutes create
                # 10 completed minutes.
                for minute in range(11):
                    handle.write(
                        "2026-09-03T14:"
                        f"{minute:02d}:01+00:00,"
                        f"AAA,{100 + minute}\n"
                    )

            try:
                first = worker.cycle()

                self.assertEqual(
                    first.completed_minutes,
                    3,
                )

                # Current implementation has already
                # read ahead. Seven completed minutes
                # remain only in process memory.
                self.assertEqual(
                    len(worker._pending_minutes),
                    7,
                )
            finally:
                worker.close()

            # Simulate production process death/restart.
            #
            # Production starts a fresh feed at the current
            # end of the tape. Without a durable committed
            # cursor, the seven read-ahead but unprocessed
            # completed minutes are therefore lost.
            root_path = Path(root)

            restarted = FactoryShadowWorker(
                tape_path=tape,
                registry_path=root_path / "registry.json",
                spec_path=root_path / "specs.json",
                state_path=root_path / "state.json",
                signal_path=root_path / "signals.jsonl",
                max_shadow_modules=2,
                max_minutes_per_cycle=3,
                history_minutes=75,
                start_at_end=True,
                resource_governor=None,
                resource_data_root=root_path,
            )

            try:
                recovered = [
                    restarted.cycle().completed_minutes,
                    restarted.cycle().completed_minutes,
                    restarted.cycle().completed_minutes,
                ]

                # Desired restart-safe behavior:
                # all seven unprocessed completed
                # minutes must still be recoverable.
                self.assertEqual(
                    recovered,
                    [3, 3, 1],
                )
            finally:
                restarted.close()


class FactoryWorkerCrashAtomicityTests(
    FactoryWorkerRestartBacklogTests
):
    def test_failed_minute_remains_durable_for_restart(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            worker, tape = self.make_worker(root)

            with tape.open("a") as handle:
                for minute in range(5):
                    handle.write(
                        "2026-09-03T15:"
                        f"{minute:02d}:01+00:00,"
                        f"AAA,{100 + minute}\n"
                    )

            original_evaluate = worker.runtime.evaluate

            def fail_processing(rows):
                # Force materialization so feature
                # generation has occurred, then crash
                # before the minute can be committed.
                list(rows)
                raise RuntimeError("simulated crash")

            worker.runtime.evaluate = fail_processing

            try:
                with self.assertRaisesRegex(
                    RuntimeError,
                    "simulated crash",
                ):
                    worker.cycle()

                # Four completed minutes were read and
                # durably queued. Since processing of
                # the first failed, none may be removed.
                self.assertEqual(
                    len(worker._pending_minutes),
                    4,
                )

                state = json.loads(
                    worker.worker_state_path.read_text()
                )

                self.assertEqual(
                    len(state["pending_minutes"]),
                    4,
                )
            finally:
                worker.runtime.evaluate = original_evaluate
                worker.close()

            restarted = FactoryShadowWorker(
                tape_path=tape,
                registry_path=root_path / "registry.json",
                spec_path=root_path / "specs.json",
                state_path=root_path / "state.json",
                signal_path=root_path / "signals.jsonl",
                worker_state_path=(
                    root_path / "worker_state.json"
                ),
                max_shadow_modules=2,
                max_minutes_per_cycle=3,
                history_minutes=75,
                start_at_end=True,
                resource_governor=None,
                resource_data_root=root_path,
            )

            try:
                first = restarted.cycle()
                second = restarted.cycle()

                self.assertEqual(
                    [
                        first.completed_minutes,
                        second.completed_minutes,
                    ],
                    [3, 1],
                )

                self.assertEqual(
                    len(restarted._pending_minutes),
                    0,
                )

                state = json.loads(
                    restarted.worker_state_path.read_text()
                )

                self.assertEqual(
                    state["pending_minutes"],
                    [],
                )
            finally:
                restarted.close()
