import unittest

from research_tools.module_factory.data_capabilities import (
    DataCapabilities,
    DataCapability,
    assess_idea,
    current_factory_capabilities,
)
from research_tools.module_factory.idea_library import (
    ResearchIdea,
)


class DataCapabilitiesTests(unittest.TestCase):
    def test_price_idea_is_fully_testable(self):
        idea = ResearchIdea(
            concept="momentum",
            mechanism="Test price persistence.",
            observables=(
                "return",
                "volatility",
            ),
        )

        result = assess_idea(
            idea,
            current_factory_capabilities(),
        )

        self.assertEqual(
            result.status,
            "FULLY_TESTABLE",
        )

        self.assertEqual(
            result.fidelity,
            1.0,
        )

    def test_volume_idea_uses_proxy_without_claiming_full_fidelity(self):
        idea = ResearchIdea(
            concept="volume_only",
            mechanism="Test volume.",
            observables=("volume",),
        )

        result = assess_idea(
            idea,
            current_factory_capabilities(),
        )

        self.assertEqual(
            result.status,
            "PARTIALLY_TESTABLE",
        )

        self.assertIn(
            "volume<-quote_activity",
            result.substituted,
        )

        self.assertGreater(
            result.fidelity,
            0.0,
        )

        self.assertLess(
            result.fidelity,
            1.0,
        )

    def test_volume_proxy_does_not_make_volume_available(self):
        caps = current_factory_capabilities()

        self.assertFalse(
            caps.available("volume")
        )

        self.assertTrue(
            caps.available("quote_activity")
        )

    def test_mixed_idea_is_partially_testable(self):
        idea = ResearchIdea(
            concept="price_volume",
            mechanism="Test price and volume.",
            observables=(
                "return",
                "volume",
            ),
        )

        result = assess_idea(
            idea,
            current_factory_capabilities(),
        )

        self.assertEqual(
            result.status,
            "PARTIALLY_TESTABLE",
        )

        self.assertGreater(
            result.fidelity,
            0.0,
        )

        self.assertLess(
            result.fidelity,
            1.0,
        )

    def test_substitute_reduces_fidelity(self):
        capabilities = DataCapabilities(
            (
                DataCapability(
                    "quote_activity",
                    True,
                ),
            )
        )

        idea = ResearchIdea(
            concept="volume_proxy",
            mechanism="Test activity.",
            observables=("volume",),
        )

        result = assess_idea(
            idea,
            capabilities,
        )

        self.assertEqual(
            result.status,
            "PARTIALLY_TESTABLE",
        )

        self.assertEqual(
            result.substituted,
            ("volume<-quote_activity",),
        )

        self.assertGreater(
            result.fidelity,
            0.0,
        )

        self.assertLess(
            result.fidelity,
            1.0,
        )

    def test_unknown_observable_is_not_claimed_full(self):
        idea = ResearchIdea(
            concept="unknown_sensor",
            mechanism="Test unknown data.",
            observables=(
                "alien_signal",
            ),
        )

        result = assess_idea(
            idea,
            current_factory_capabilities(),
        )

        self.assertEqual(
            result.status,
            "PARTIALLY_TESTABLE",
        )

        self.assertLess(
            result.fidelity,
            1.0,
        )


if __name__ == "__main__":
    unittest.main()


class VerifiedTapeCapabilityTests(unittest.TestCase):
    def test_verified_level1_capabilities(self):
        caps = current_factory_capabilities()

        for name in (
            "bid_ask",
            "quoted_depth",
            "trade_snapshot",
            "quote_timing",
            "venue_context",
            "quote_activity",
        ):
            self.assertTrue(
                caps.available(name),
                name,
            )

    def test_full_trade_tape_not_claimed(self):
        caps = current_factory_capabilities()

        for name in (
            "volume",
            "trades",
            "order_book",
            "subminute_price",
        ):
            self.assertFalse(
                caps.available(name),
                name,
            )
