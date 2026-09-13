import unittest
from datetime import datetime, timedelta, timezone

from research_tools.cascade_reversal_study import Bar, detect_events
from research_tools.module_factory.fast_cascade import (
    extract_observations,
    filter_observations,
)


def make_bars(symbol_start: float, spy=False):
    base = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
    bars = []

    if spy:
        prices = [symbol_start - i * 0.01 for i in range(10)]
        prices += [prices[-1] + 0.02]
    else:
        prices = [
            100.00,
            99.90,
            99.80,
            99.70,
            99.60,
            99.50,
            99.40,
            99.30,
            99.20,
            99.10,
            99.25,
        ]

    while len(prices) < 36:
        prices.append(prices[-1] + 0.03)

    for i, price in enumerate(prices):
        bars.append(
            Bar(
                minute=base + timedelta(minutes=i),
                open=price,
                high=price,
                low=price,
                close=price,
            )
        )

    return bars


class FastCascadeTests(unittest.TestCase):
    def setUp(self):
        self.bars = {
            "ABC": make_bars(100.0),
            "SPY": make_bars(500.0, spy=True),
        }

    def test_fast_filter_matches_reference_detector(self):
        reference = detect_events(
            self.bars,
            window_minutes=10,
            min_drop_pct=0.75,
            min_down_minutes=6,
            near_low_bps=10.0,
            max_single_minute_drop_pct=0.50,
            max_spy_drop_pct=0.50,
            cooldown_minutes=20,
            horizons=(10, 20),
            cost_bps=0.0,
        )

        observations = extract_observations(
            self.bars,
            window_minutes=10,
            horizons=(10, 20),
        )

        fast = filter_observations(
            observations,
            min_drop_pct=0.75,
            min_down_minutes=6,
            near_low_bps=10.0,
            max_single_minute_drop_pct=0.50,
            max_spy_drop_pct=0.50,
            cooldown_minutes=20,
        )

        self.assertEqual(len(fast), len(reference))

        self.assertEqual(
            [(x.symbol, x.minute) for x in fast],
            [(x.symbol, x.minute) for x in reference],
        )

        for fast_event, reference_event in zip(fast, reference):
            self.assertAlmostEqual(
                fast_event.returns[10],
                reference_event.returns[10],
            )
            self.assertAlmostEqual(
                fast_event.returns[20],
                reference_event.returns[20],
            )

    def test_extraction_is_broader_than_filter(self):
        observations = extract_observations(
            self.bars,
            window_minutes=10,
            horizons=(10, 20),
        )

        filtered = filter_observations(
            observations,
            min_drop_pct=0.75,
            min_down_minutes=6,
            near_low_bps=10.0,
            max_single_minute_drop_pct=0.50,
            max_spy_drop_pct=0.50,
            cooldown_minutes=20,
        )

        self.assertGreaterEqual(len(observations), len(filtered))


if __name__ == "__main__":
    unittest.main()
