import unittest
from datetime import datetime, timedelta, timezone

from research_tools.module_factory.live_feature_engine import (
    LiveFeatureEngine,
)
from research_tools.module_factory.live_minute_feed import (
    CompletedMinute,
)


class LiveFeatureEngineTests(unittest.TestCase):
    def minute(
        self,
        index,
        *,
        aaa=None,
        spy=None,
    ):
        base = datetime(
            2026,
            9,
            3,
            14,
            0,
            tzinfo=timezone.utc,
        )

        prices = {}

        if aaa is not None:
            prices["AAA"] = aaa

        if spy is not None:
            prices["SPY"] = spy

        return CompletedMinute(
            minute=base
            + timedelta(minutes=index),
            prices=prices,
        )

    def test_requires_full_60_minute_history(self):
        engine = LiveFeatureEngine()

        rows = ()

        for index in range(60):
            rows = engine.consume(
                self.minute(
                    index,
                    aaa=100 + index,
                    spy=500 + index,
                )
            )

        self.assertEqual(rows, ())

        rows = engine.consume(
            self.minute(
                60,
                aaa=160,
                spy=560,
            )
        )

        self.assertEqual(len(rows), 1)

    def test_return_30_is_correct(self):
        engine = LiveFeatureEngine()

        rows = ()

        for index in range(61):
            rows = engine.consume(
                self.minute(
                    index,
                    aaa=100 + index,
                    spy=500 + index,
                )
            )

        feature = rows[0].features[
            "return_30"
        ]

        expected = 100.0 * (
            160.0 / 130.0 - 1.0
        )

        self.assertAlmostEqual(
            feature,
            expected,
        )

    def test_spy_relative_return_is_correct(self):
        engine = LiveFeatureEngine()

        rows = ()

        for index in range(61):
            rows = engine.consume(
                self.minute(
                    index,
                    aaa=100 + index * 2,
                    spy=500 + index,
                )
            )

        features = rows[0].features

        own = 100.0 * (
            220 / 160 - 1.0
        )
        spy = 100.0 * (
            560 / 530 - 1.0
        )

        self.assertAlmostEqual(
            features[
                "spy_relative_return_30"
            ],
            own - spy,
        )

    def test_gap_blocks_feature_generation(self):
        engine = LiveFeatureEngine()

        for index in range(30):
            engine.consume(
                self.minute(
                    index,
                    aaa=100 + index,
                    spy=500 + index,
                )
            )

        for index in range(31, 70):
            rows = engine.consume(
                self.minute(
                    index,
                    aaa=100 + index,
                    spy=500 + index,
                )
            )

        self.assertEqual(rows, ())

    def test_no_forward_return_fields_exist(self):
        engine = LiveFeatureEngine()

        rows = ()

        for index in range(61):
            rows = engine.consume(
                self.minute(
                    index,
                    aaa=100 + index,
                    spy=500 + index,
                )
            )

        features = rows[0].features

        self.assertFalse(
            any(
                name.startswith("forward")
                for name in features
            )
        )

        self.assertFalse(
            any(
                "future" in name
                for name in features
            )
        )

    def test_live_vocabulary_contains_key_discovery_features(self):
        engine = LiveFeatureEngine()

        rows = ()

        for index in range(61):
            price = (
                100
                + index
                + (index % 7) * 0.1
            )

            rows = engine.consume(
                self.minute(
                    index,
                    aaa=price,
                    spy=500 + index * 0.25,
                )
            )

        features = rows[0].features

        required = {
            "return_30",
            "return_60",
            "kurtosis_60",
            "skew_60",
            "acceleration_20",
            "spy_relative_return_30",
        }

        self.assertTrue(
            required.issubset(
                features.keys()
            )
        )


if __name__ == "__main__":
    unittest.main()
