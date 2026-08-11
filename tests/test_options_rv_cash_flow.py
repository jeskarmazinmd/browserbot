import unittest

from options_rv_paper_tracker import OptionsRVTracker


class OptionsRVCashFlowTests(unittest.TestCase):
    def test_close_reverses_opening_transaction_signs(self):
        tracker = object.__new__(OptionsRVTracker)
        tracker.commission = 0.65
        legs = [
            {"side": "SELL", "quantity": 1, "bid": 4.73, "ask": 4.79},
            {"side": "BUY", "quantity": 1, "bid": 14.38, "ask": 14.65},
        ]
        opening, _ = tracker._cash_flow(legs, True)
        closing, _ = tracker._cash_flow(legs, False)
        self.assertAlmostEqual(opening, -993.3)
        self.assertAlmostEqual(closing, 957.7)
        self.assertAlmostEqual(opening + closing, -35.6)


if __name__ == "__main__":
    unittest.main()
