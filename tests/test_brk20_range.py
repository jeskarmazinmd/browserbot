import unittest
from datetime import datetime, timedelta, timezone

from engine.events import MarketSnapshot, Quote
from strategies.strategy_brk20 import Strategy


class BRK20RangeTests(unittest.TestCase):
    def signals(self, prices):
        strategy = Strategy()
        start = datetime(2026, 9, 24, 14, 0, tzinfo=timezone.utc)
        result = []
        for index, price in enumerate(prices):
            result = strategy.on_snapshot(MarketSnapshot(
                timestamp=start + timedelta(minutes=index),
                quotes={"SPY": Quote(price=price)},
                expected_symbol_count=1, returned_symbol_count=1,
                fetch_duration_seconds=0,
            ))
        return result

    def test_wide_prior_range_is_not_a_breakout_setup(self):
        self.assertEqual(self.signals([100] * 19 + [103, 104]), [])
        self.assertEqual(len(self.signals([100] * 20 + [100.2])), 1)


if __name__ == "__main__":
    unittest.main()
