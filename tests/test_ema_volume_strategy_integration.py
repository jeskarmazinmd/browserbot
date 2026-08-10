from __future__ import annotations

from datetime import datetime, timezone
import unittest

from engine.events import MarketSnapshot, Quote
from strategies.strategy_ema1 import EMA1Strategy, _State as EMA1State
from strategies.strategy_ema1rr import Strategy as EMA1RRStrategy, _State as EMA1RRState


def crossover_snapshot(provider):
    return MarketSnapshot(
        timestamp=datetime(2026, 8, 10, 19, 30, tzinfo=timezone.utc),
        quotes={"AAPL": Quote(price=102.0), "MSFT": Quote(price=102.0)},
        expected_symbol_count=2,
        returned_symbol_count=2,
        fetch_duration_seconds=0.0,
        metadata={"confirm_recent_volume_ratios": provider},
    )


class EMAVolumeStrategyIntegrationTests(unittest.TestCase):
    def _assert_one_batch_and_two_signals(self, strategy, state_type):
        strategy._state = {
            symbol: state_type(observations_seen=24, fast=99.9, slow=100.0)
            for symbol in ("AAPL", "MSFT")
        }
        calls = []

        def provider(symbols, timestamp):
            calls.append((list(symbols), timestamp))
            return {symbol: 1.5 for symbol in symbols}

        signals = strategy.on_snapshot(crossover_snapshot(provider))
        self.assertEqual(len(calls), 1)
        self.assertCountEqual(calls[0][0], ["AAPL", "MSFT"])
        self.assertCountEqual([signal.symbol for signal in signals], ["AAPL", "MSFT"])

    def test_ema1_batches_crossovers(self):
        self._assert_one_batch_and_two_signals(EMA1Strategy(), EMA1State)

    def test_ema1rr_batches_crossovers(self):
        self._assert_one_batch_and_two_signals(EMA1RRStrategy(), EMA1RRState)

    def test_unavailable_confirmation_fails_closed(self):
        strategy = EMA1Strategy()
        strategy._state = {
            "AAPL": EMA1State(observations_seen=24, fast=99.9, slow=100.0)
        }
        snapshot = MarketSnapshot(
            timestamp=datetime(2026, 8, 10, 19, 30, tzinfo=timezone.utc),
            quotes={"AAPL": Quote(price=102.0)},
            expected_symbol_count=1,
            returned_symbol_count=1,
            fetch_duration_seconds=0.0,
            metadata={"confirm_recent_volume_ratios": lambda symbols, timestamp: {}},
        )
        self.assertEqual(strategy.on_snapshot(snapshot), [])


if __name__ == "__main__":
    unittest.main()
