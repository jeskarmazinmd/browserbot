import unittest

from market_quotes import extract_quote_snapshot, legacy_scalar_price


class MarketQuoteTests(unittest.TestCase):
    def test_extracts_execution_snapshot_without_conflating_prices(self):
        payload = {
            "realtime": True,
            "quote": {
                "lastPrice": 100.02,
                "mark": 100.00,
                "bidPrice": 99.98,
                "askPrice": 100.04,
                "lastSize": 7,
                "bidSize": 120,
                "askSize": 80,
                "quoteTime": 1000,
                "tradeTime": 1001,
                "bidTime": 998,
                "askTime": 999,
                "lastMICId": "XADF",
                "bidMICId": "ARCX",
                "askMICId": "ARCX",
            },
            "regular": {
                "regularMarketLastPrice": 99.95,
                "regularMarketTradeTime": 990,
            },
            "extended": {"lastPrice": 100.10},
        }

        q = extract_quote_snapshot("spy", payload)

        self.assertEqual(q.symbol, "SPY")
        self.assertEqual(q.legacy_price, 100.02)
        self.assertEqual(q.last, 100.02)
        self.assertEqual(q.mark, 100.00)
        self.assertEqual(q.bid, 99.98)
        self.assertEqual(q.ask, 100.04)
        self.assertEqual(q.bid_size_raw, 120)
        self.assertEqual(q.ask_size_raw, 80)
        self.assertEqual(q.regular_last, 99.95)
        self.assertEqual(q.extended_last, 100.10)
        self.assertTrue(q.realtime)

    def test_legacy_price_keeps_original_fallback_order(self):
        self.assertEqual(
            legacy_scalar_price({
                "quote": {
                    "lastPrice": 100.0,
                    "mark": 99.9,
                    "bidPrice": 99.8,
                    "askPrice": 100.2,
                }
            }),
            100.0,
        )

        self.assertEqual(
            legacy_scalar_price({
                "quote": {
                    "lastPrice": 0,
                    "mark": 99.9,
                    "bidPrice": 99.8,
                    "askPrice": 100.2,
                }
            }),
            99.9,
        )

    def test_legacy_price_can_fall_back_to_bid_or_ask(self):
        self.assertEqual(
            legacy_scalar_price({"quote": {"bidPrice": 99.8}}),
            99.8,
        )
        self.assertEqual(
            legacy_scalar_price({"quote": {"askPrice": 100.2}}),
            100.2,
        )

    def test_legacy_scalar_matches_frozen_pre_migration_algorithm(self):
        def frozen_old(payload):
            if not isinstance(payload, dict):
                return None
            containers=[payload]
            for key in ["quote","regular","extended","reference"]:
                if isinstance(payload.get(key),dict):
                    containers.append(payload[key])
            keys=[
                "lastPrice","mark","regularMarketLastPrice",
                "closePrice","bidPrice","askPrice",
            ]
            for obj in containers:
                for key in keys:
                    value=obj.get(key)
                    try:
                        if value is not None and float(value)>0:
                            return float(value)
                    except Exception:
                        pass
            return None

        payloads=[
            None,
            {},
            {"lastPrice":12.0},
            {"quote":{"lastPrice":11.0,"mark":10.0}},
            {"quote":{"lastPrice":0,"mark":10.0}},
            {"quote":{"mark":0,"bidPrice":9.9,"askPrice":10.1}},
            {"regular":{"regularMarketLastPrice":8.0}},
            {"extended":{"lastPrice":7.0}},
            {"quote":{"lastPrice":"bad","askPrice":"6.5"}},
            {"quote":{"bidPrice":0,"askPrice":5.5}},
            {
                "quote":{"lastPrice":0,"mark":0},
                "regular":{"regularMarketLastPrice":4.5},
            },
        ]

        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual(
                    legacy_scalar_price(payload),
                    frozen_old(payload),
                )

    def test_missing_execution_fields_remain_missing(self):
        q = extract_quote_snapshot("XYZ", {"quote": {"lastPrice": 10}})
        self.assertEqual(q.last, 10)
        self.assertIsNone(q.bid)
        self.assertIsNone(q.ask)
        self.assertIsNone(q.bid_size_raw)
        self.assertIsNone(q.ask_size_raw)


if __name__ == "__main__":
    unittest.main()
