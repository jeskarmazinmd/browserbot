from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from engine.events import MarketSnapshot, Quote
from strategies.registry import (
    MinuteStrategyPool,
    _balanced_shards,
    _minute_strategy_specs,
)


def snapshots(count=35):
    start = datetime(2026, 8, 10, 13, 30, tzinfo=timezone.utc)
    symbols = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMD", "MU", "AVGO"]
    result = []
    for minute in range(count):
        quotes = {
            symbol: Quote(
                price=100.0 + index + minute * (0.03 + index * 0.002),
                total_volume=1_000_000 + minute * 10_000,
            )
            for index, symbol in enumerate(symbols)
        }
        result.append(
            MarketSnapshot(
                timestamp=start + timedelta(minutes=minute),
                quotes=quotes,
                expected_symbol_count=len(symbols),
                returned_symbol_count=len(symbols),
                fetch_duration_seconds=0.0,
            )
        )
    return result


def signature(signals):
    return [
        (
            signal.strategy_id,
            signal.symbol,
            signal.signal_type,
            signal.timestamp,
            signal.data,
        )
        for signal in signals
    ]


class MinuteStrategyPoolTests(unittest.TestCase):
    def test_balancing_assigns_every_strategy_once(self):
        specs = _minute_strategy_specs()
        shards = _balanced_shards(specs, 4)
        assigned = [spec for shard in shards for spec in shard]
        self.assertCountEqual(assigned, specs)
        self.assertEqual(len(assigned), len(set(assigned)))

    def test_parallel_pool_matches_single_process(self):
        serial = MinuteStrategyPool(shard_count=1, timeout_seconds=30)
        parallel = MinuteStrategyPool(shard_count=4, timeout_seconds=30)
        try:
            for snapshot in snapshots():
                serial_signals, serial_errors = serial.evaluate(snapshot)
                parallel_signals, parallel_errors = parallel.evaluate(snapshot)
                self.assertEqual(serial_errors, [])
                self.assertEqual(parallel_errors, [])
                self.assertEqual(signature(parallel_signals), signature(serial_signals))
        finally:
            serial.close()
            parallel.close()

    def test_dead_shard_is_restarted_without_terminating_pool(self):
        pool = MinuteStrategyPool(shard_count=2, timeout_seconds=30)
        try:
            failed_shard = list(pool.workers[0][2])
            old_process = pool.workers[0][0]
            old_process.terminate()
            old_process.join(timeout=2)

            signals, errors = pool.evaluate(snapshots(1)[0])

            self.assertIsInstance(signals, list)
            self.assertEqual(
                {strategy_id for strategy_id, _ in errors},
                {spec[0] for spec in failed_shard},
            )
            self.assertTrue(pool.workers[0][0].is_alive())
            self.assertNotEqual(pool.workers[0][0].pid, old_process.pid)
            self.assertFalse(pool.closed)
        finally:
            pool.close()

    def test_timeout_restarts_shards_without_system_exit(self):
        pool = MinuteStrategyPool(shard_count=2, timeout_seconds=0)
        try:
            signals, errors = pool.evaluate(snapshots(1)[0])

            self.assertEqual(signals, [])
            self.assertEqual(
                {strategy_id for strategy_id, _ in errors},
                {spec[0] for spec in pool.specs},
            )
            self.assertTrue(all(process.is_alive() for process, _, _ in pool.workers))
            self.assertFalse(pool.closed)
        finally:
            pool.close()

    def test_broken_pipe_restarts_only_affected_shard(self):
        pool = MinuteStrategyPool(shard_count=2, timeout_seconds=30)
        try:
            failed_shard = list(pool.workers[0][2])
            old_process = pool.workers[0][0]
            pool.workers[0][1].close()

            signals, errors = pool.evaluate(snapshots(1)[0])

            self.assertIsInstance(signals, list)
            self.assertEqual(
                {strategy_id for strategy_id, _ in errors},
                {spec[0] for spec in failed_shard},
            )
            self.assertTrue(pool.workers[0][0].is_alive())
            self.assertNotEqual(pool.workers[0][0].pid, old_process.pid)
            self.assertFalse(pool.closed)
        finally:
            pool.close()


if __name__ == "__main__":
    unittest.main()
