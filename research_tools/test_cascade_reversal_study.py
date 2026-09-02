import unittest
from datetime import datetime, timedelta, timezone

from research_tools.cascade_reversal_study import Bar, detect_events


def make_bars(symbol, closes):
    start = datetime(2026, 9, 2, 15, 40, tzinfo=timezone.utc)
    bars = []
    previous = closes[0]
    for index, close in enumerate(closes):
        bars.append(
            Bar(
                minute=start + timedelta(minutes=index),
                open=previous,
                high=max(previous, close) + 0.01,
                low=min(previous, close) - 0.01,
                close=close,
            )
        )
        previous = close
    return symbol, bars


class CascadeReversalStudyTests(unittest.TestCase):
    def test_detects_confirmed_gradual_cascade(self):
        # Ten mostly negative minutes, a positive confirmation minute, then a
        # sustained recovery.  No individual minute is a flash crash.
        stock = [
            100.00, 99.90, 99.82, 99.73, 99.65, 99.58, 99.50, 99.42,
            99.35, 99.27, 99.20, 99.28, 99.38, 99.48, 99.58, 99.68,
            99.78, 99.88, 99.98, 100.08, 100.18, 100.28, 100.38,
            100.48, 100.58, 100.68, 100.78, 100.88, 100.98, 101.08,
            101.18, 101.28,
        ]
        spy = [100.0] * len(stock)
        events = detect_events(dict([make_bars("AAPL", stock), make_bars("SPY", spy)]))
        self.assertEqual(1, len(events))
        self.assertEqual("AAPL", events[0].symbol)
        self.assertGreater(events[0].returns[15], 0)

    def test_rejects_unconfirmed_fall(self):
        stock = [100.0 - 0.1 * index for index in range(32)]
        spy = [100.0] * len(stock)
        events = detect_events(dict([make_bars("AAPL", stock), make_bars("SPY", spy)]))
        self.assertEqual([], events)

    def test_rejects_broad_market_cascade(self):
        stock = [100.0 - 0.08 * index for index in range(11)] + [99.28]
        stock += [99.38 + 0.1 * index for index in range(20)]
        spy = [100.0 - 0.08 * index for index in range(11)] + [99.28]
        spy += [99.38 + 0.1 * index for index in range(20)]
        events = detect_events(dict([make_bars("AAPL", stock), make_bars("SPY", spy)]))
        self.assertEqual([], events)


if __name__ == "__main__":
    unittest.main()
