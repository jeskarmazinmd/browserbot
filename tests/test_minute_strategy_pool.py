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


if __name__ == "__main__":
    unittest.main()
