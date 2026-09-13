import math
import unittest

from research_tools.module_factory.market_observations import (
    MarketObservation,
)
from research_tools.module_factory.microstructure_features import (
    derive_microstructure_features,
)


def observation(
    *,
    bid=99.0,
    ask=101.0,
    bid_size=300.0,
    ask_size=100.0,
):
    return MarketObservation(
        market_minute_utc=(
            "2026-08-28T13:35:00+00:00"
        ),
        observed_at_utc=(
            "2026-08-28T13:35:10+00:00"
        ),
        symbol="TEST",
        price=100.0,
        last=100.5,
        mark=100.0,
        bid=bid,
        ask=ask,
        last_size=100.0,
        bid_size=bid_size,
        ask_size=ask_size,
        quote_time_ms=1787924110000,
        trade_time_ms=1787924109000,
        bid_time_ms=1787924108000,
        ask_time_ms=1787924110000,
        regular_last=100.5,
        regular_trade_time_ms=(
            1787924109000
        ),
        extended_last=math.nan,
        last_mic="XNAS",
        bid_mic="XNAS",
        ask_mic="XNYS",
        realtime=True,
    )


class MicrostructureFeatureTests(
    unittest.TestCase
):
    def test_spread_and_midpoint(self):
        features = (
            derive_microstructure_features(
                observation()
            )
        )

        self.assertAlmostEqual(
            features.midpoint,
            100.0,
        )
        self.assertAlmostEqual(
            features.spread,
            2.0,
        )
        self.assertAlmostEqual(
            features.spread_bps,
            200.0,
        )

    def test_depth_imbalance(self):
        features = (
            derive_microstructure_features(
                observation()
            )
        )

        self.assertAlmostEqual(
            features.depth_imbalance,
            0.5,
        )

    def test_microprice_moves_toward_ask_when_bid_deeper(self):
        features = (
            derive_microstructure_features(
                observation()
            )
        )

        self.assertGreater(
            features.microprice,
            features.midpoint,
        )

    def test_quote_and_trade_age(self):
        obs = observation()

        features = (
            derive_microstructure_features(
                obs
            )
        )

        self.assertTrue(
            math.isfinite(
                features.quote_age_ms
            )
        )

        self.assertTrue(
            math.isfinite(
                features.trade_age_ms
            )
        )

    def test_missing_quote_is_safe(self):
        features = (
            derive_microstructure_features(
                observation(
                    bid=math.nan,
                )
            )
        )

        self.assertTrue(
            math.isnan(
                features.spread_bps
            )
        )

    def test_venue_relationship(self):
        features = (
            derive_microstructure_features(
                observation()
            )
        )

        self.assertEqual(
            features.trade_bid_same_venue,
            1.0,
        )

        self.assertEqual(
            features.bid_ask_same_venue,
            0.0,
        )


if __name__ == "__main__":
    unittest.main()
