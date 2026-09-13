import unittest

from research_tools.module_factory.market_observations import (
    from_schwab_row,
)


class MarketObservationTests(unittest.TestCase):
    def test_schwab_translation(self):
        row = {
            "market_minute_utc":
                "2026-08-28T13:35:00+00:00",
            "observed_at_utc":
                "2026-08-28T13:35:58.995991+00:00",
            "symbol": "A",
            "legacy_price": "155.29",
            "last": "155.29",
            "mark": "155.29",
            "bid": "155.23",
            "ask": "155.69",
            "last_size_raw": "100.0",
            "bid_size_raw": "100.0",
            "ask_size_raw": "100.0",
            "quote_time_ms": "1787924154621",
            "trade_time_ms": "1787924154325",
            "bid_time_ms": "1787924152857",
            "ask_time_ms": "1787924154621",
            "regular_last": "155.29",
            "regular_trade_time_ms":
                "1787924154325",
            "extended_last": "",
            "last_mic": "EDGX",
            "bid_mic": "EDGX",
            "ask_mic": "XNYS",
            "realtime": "True",
        }

        obs = from_schwab_row(row)

        self.assertEqual(obs.symbol, "A")
        self.assertAlmostEqual(
            obs.bid,
            155.23,
        )
        self.assertAlmostEqual(
            obs.ask,
            155.69,
        )
        self.assertEqual(
            obs.bid_time_ms,
            1787924152857,
        )
        self.assertTrue(obs.realtime)

    def test_missing_optional_values_are_safe(self):
        obs = from_schwab_row(
            {
                "symbol": "XYZ",
                "observed_at_utc":
                    "2026-08-28T13:35:00+00:00",
            }
        )

        self.assertEqual(
            obs.symbol,
            "XYZ",
        )
        self.assertIsNone(
            obs.trade_time_ms,
        )


if __name__ == "__main__":
    unittest.main()
