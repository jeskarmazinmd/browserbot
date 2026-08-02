from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType

import pandas as pd

from engine.events import MarketSnapshot, Quote, SignalEvent
from strategies.registry import (
    ENABLED_STRATEGIES,
    FAILED_STRATEGIES,
    FLASH_STRATEGIES,
    MINUTE_STRATEGIES,
    TICK_STRATEGIES,
)


ROOT = Path(__file__).resolve().parents[1]


class MultiFrameSource:
    def __init__(self, frames):
        self.frames = frames
        self.index = -1

    def read_data(self):
        self.index = min(
            self.index + 1,
            len(self.frames) - 1,
        )
        return self.frames[self.index]

    def now(self):
        index = max(self.index, 0)
        return self.frames[index]["timestamp"].max()

    @property
    def finished(self):
        return self.index >= len(self.frames) - 1


def strategy_ids(strategies):
    return [
        str(
            getattr(
                strategy,
                "name",
                getattr(strategy, "STRATEGY_ID", ""),
            )
        )
        for strategy in strategies
    ]


def import_runner(run_id):
    os.environ["RUN_MODE"] = "REPLAY"
    os.environ["RUN_ID"] = run_id
    os.environ["REPLAY_TAPE_PATH"] = "unused.csv"

    if "schwab_clients" not in sys.modules:
        stub = ModuleType("schwab_clients")

        class SchwabTradeClient:
            pass

        stub.SchwabTradeClient = SchwabTradeClient
        sys.modules["schwab_clients"] = stub

    for name in ["bot_output", "live_strategy_runner"]:
        sys.modules.pop(name, None)

    return importlib.import_module("live_strategy_runner")


class MinuteCadencePipelineTests(unittest.TestCase):

    def tearDown(self):
        os.environ.pop("RUN_MODE", None)
        os.environ.pop("RUN_ID", None)
        os.environ.pop("REPLAY_TAPE_PATH", None)

    def test_registry_partition(self):
        all_ids = strategy_ids(ENABLED_STRATEGIES)
        flash_ids = strategy_ids(FLASH_STRATEGIES)
        tick_ids = strategy_ids(TICK_STRATEGIES)
        minute_ids = strategy_ids(MINUTE_STRATEGIES)

        self.assertEqual(30, len(all_ids))
        self.assertEqual(4, len(flash_ids))
        self.assertEqual(0, len(tick_ids))
        self.assertEqual(30, len(minute_ids))
        self.assertEqual(
            set(all_ids),
            set(tick_ids) | set(minute_ids),
        )
        self.assertEqual(
            34,
            len(set(flash_ids) | set(all_ids)),
        )
        self.assertFalse(set(flash_ids) & set(tick_ids))
        self.assertFalse(set(flash_ids) & set(minute_ids))
        self.assertFalse(set(tick_ids) & set(minute_ids))
        self.assertEqual([], FAILED_STRATEGIES)

    def test_completed_minute_withholding(self):
        runner = import_runner("minute_boundary")
        start = datetime(
            2026,
            8,
            3,
            14,
            0,
            tzinfo=timezone.utc,
        )

        rows = []

        for minute in range(3):
            timestamp = start + timedelta(minutes=minute)
            rows.extend([
                (timestamp, "AAA", 100.0 + minute),
                (timestamp, "BBB", 50.0 + minute),
            ])

        frame = pd.DataFrame(
            rows,
            columns=["timestamp", "symbol", "price"],
        )

        snapshots = runner.completed_minute_snapshots(frame)

        self.assertEqual(2, len(snapshots))
        self.assertEqual(start, snapshots[0].timestamp)
        self.assertEqual(
            start + timedelta(minutes=1),
            snapshots[1].timestamp,
        )

        later = runner.completed_minute_snapshots(
            frame,
            after_timestamp=start,
        )

        self.assertEqual(1, len(later))
        self.assertEqual(
            start + timedelta(minutes=1),
            later[0].timestamp,
        )

    def test_minute_history_is_bounded(self):
        start = datetime(
            2026,
            8,
            3,
            14,
            0,
            tzinfo=timezone.utc,
        )

        for minute in range(70):
            snapshot = MarketSnapshot(
                timestamp=start + timedelta(minutes=minute),
                quotes={
                    "AAA": Quote(price=100.0 + minute * 0.01),
                    "BBB": Quote(price=50.0 + minute * 0.005),
                    "SPY": Quote(price=500.0 + minute * 0.01),
                },
                expected_symbol_count=3,
                returned_symbol_count=3,
                fetch_duration_seconds=0.0,
                metadata={"cadence": "minute"},
            )

            for strategy in MINUTE_STRATEGIES:
                strategy.on_snapshot(snapshot)

        largest = 0

        for strategy in MINUTE_STRATEGIES:
            for state in getattr(strategy, "_state", {}).values():
                observations = getattr(
                    state,
                    "observations",
                    None,
                )

                if observations is not None:
                    largest = max(
                        largest,
                        len(observations),
                    )

        self.assertLessEqual(largest, 67)

    def test_runner_warms_then_logs_new_minute_signal(self):
        runner = import_runner("minute_runner_e2e")

        start = pd.Timestamp("2026-08-03T14:00:00Z")

        first = pd.DataFrame(
            [
                (start, "TEST", 100.0),
                (start + pd.Timedelta(minutes=1), "TEST", 100.1),
                (start + pd.Timedelta(minutes=2), "TEST", 100.2),
            ],
            columns=["timestamp", "symbol", "price"],
        )

        second = pd.concat(
            [
                first,
                pd.DataFrame(
                    [
                        (
                            start + pd.Timedelta(minutes=3),
                            "TEST",
                            100.3,
                        )
                    ],
                    columns=["timestamp", "symbol", "price"],
                ),
            ],
            ignore_index=True,
        )

        runner.quote_source = MultiFrameSource([first, second])
        runner.load_positions = lambda: {}
        runner.detect_latest_flash = lambda *args, **kwargs: None
        runner.minute_prices = lambda group: pd.Series(
            dtype=float
        )

        dispatched = []

        def fake_minute_dispatch(snapshot):
            dispatched.append(snapshot.timestamp)

            if len(dispatched) <= 2:
                return [], []

            return [
                SignalEvent(
                    timestamp=snapshot.timestamp,
                    strategy_id="GT1",
                    symbol="TEST",
                    signal_type="SIGNAL",
                    data={
                        "entry_price": 100.2,
                        "target_price": 100.9,
                        "stop_price": 99.5,
                        "setup": "test_minute_signal",
                        "live_order_placement": False,
                    },
                )
            ], []

        runner.run_minute_strategies = fake_minute_dispatch

        shutil.rmtree(
            runner.DATA_ROOT,
            ignore_errors=True,
        )
        runner.DATA_ROOT.mkdir(
            parents=True,
            exist_ok=True,
        )

        runner.main()

        events_path = runner.DATA_ROOT / "bot_events.jsonl"
        self.assertTrue(events_path.exists())

        events = [
            json.loads(line)
            for line in events_path.read_text().splitlines()
            if line.strip()
        ]

        signals = [
            event
            for event in events
            if event.get("event_type") == "SIGNAL"
            and event.get("strategy_id") == "GT1"
        ]

        self.assertEqual(1, len(signals))
        self.assertEqual(
            "minute",
            signals[0]["thresholds"]["CADENCE"],
        )
        self.assertEqual(
            "test_minute_signal",
            signals[0]["signal"]["setup"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
