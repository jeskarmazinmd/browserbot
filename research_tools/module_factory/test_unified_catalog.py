import unittest

from research_tools.module_factory.unified_catalog import (
    ancestry_map,
    features_by_ancestry,
    observation_feature_catalog,
    price_feature_catalog,
    unified_catalog_by_name,
    unified_feature_catalog,
)


class UnifiedCatalogTests(
    unittest.TestCase
):
    def test_expected_catalog_size(self):
        self.assertEqual(
            len(price_feature_catalog()),
            49,
        )

        self.assertEqual(
            len(
                observation_feature_catalog()
            ),
            55,
        )

        self.assertEqual(
            len(
                unified_feature_catalog()
            ),
            104,
        )

    def test_catalog_names_are_unique(self):
        catalog = (
            unified_feature_catalog()
        )

        names = [
            feature.name
            for feature in catalog
        ]

        self.assertEqual(
            len(names),
            len(set(names)),
        )

    def test_price_ancestry(self):
        catalog = (
            unified_catalog_by_name()
        )

        self.assertEqual(
            catalog[
                "return_5"
            ].ancestry,
            ("PRICE",),
        )

        self.assertIn(
            "MARKET_CONTEXT",
            catalog[
                "spy_relative_return_5"
            ].ancestry,
        )

    def test_microstructure_ancestry(self):
        catalog = (
            unified_catalog_by_name()
        )

        self.assertIn(
            "LEVEL1_SNAPSHOT",
            catalog[
                "depth_imbalance"
            ].ancestry,
        )

        self.assertIn(
            "TEMPORAL",
            catalog[
                "spread_bps_mean_5"
            ].ancestry,
        )

    def test_ancestry_queries(self):
        level1 = features_by_ancestry(
            "LEVEL1_SNAPSHOT"
        )

        self.assertIn(
            "spread_bps",
            level1,
        )

        self.assertIn(
            "depth_imbalance_change",
            level1,
        )

        mapping = ancestry_map()

        self.assertEqual(
            len(mapping),
            104,
        )


if __name__ == "__main__":
    unittest.main()
