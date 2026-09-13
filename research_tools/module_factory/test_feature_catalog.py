import unittest

from research_tools.module_factory.feature_catalog import (
    catalog_by_name,
    microstructure_catalog,
)


class FeatureCatalogTests(
    unittest.TestCase
):
    def test_catalog_names_unique(self):
        catalog = microstructure_catalog()

        names = [
            feature.name
            for feature in catalog
        ]

        self.assertEqual(
            len(names),
            len(set(names)),
        )

    def test_catalog_has_base_microstructure(self):
        catalog = catalog_by_name()

        for name in (
            "spread_bps",
            "depth_imbalance",
            "microprice_displacement_bps",
            "trade_age_ms",
        ):
            self.assertIn(
                name,
                catalog,
            )

    def test_catalog_has_temporal_features(self):
        catalog = catalog_by_name()

        self.assertIn(
            "depth_imbalance_change",
            catalog,
        )

        self.assertIn(
            "spread_bps_mean_5",
            catalog,
        )

        self.assertIn(
            "trade_age_ms_std_10",
            catalog,
        )

    def test_ancestry_is_explicit(self):
        catalog = catalog_by_name()

        self.assertIn(
            "LEVEL1_SNAPSHOT",
            catalog[
                "spread_bps"
            ].ancestry,
        )

        self.assertIn(
            "TEMPORAL",
            catalog[
                "spread_bps_mean_5"
            ].ancestry,
        )


if __name__ == "__main__":
    unittest.main()
