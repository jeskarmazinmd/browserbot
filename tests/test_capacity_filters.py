from __future__ import annotations

import unittest

from strategies.capacity_filters import (
    CAPACITY_FILTERS,
    apply_capacity_filters,
)


class CapacityFilterTests(unittest.TestCase):

    def payload(self, strategy_id, symbol, **metrics):
        return {
            "strategy_id": strategy_id,
            "symbol": symbol,
            "timestamp": "2026-08-05T14:00:00+00:00",
            "setup_id": f"{strategy_id}|{symbol}|test",
            "universe_memberships": [],
            **metrics,
        }

    def test_every_configured_strategy_has_exactly_one_rule(self):
        self.assertEqual(31, len(CAPACITY_FILTERS))
        self.assertEqual(31, len(set(CAPACITY_FILTERS)))
        self.assertTrue(all("kind" in rule for rule in CAPACITY_FILTERS.values()))

    def test_unconfigured_strategy_passes_through(self):
        payload = self.payload("PTD1X", "AAA")
        self.assertEqual([payload], apply_capacity_filters([payload]))

    def test_rule_is_prospective_only(self):
        payload = self.payload("PD1", "HISTORICAL")
        payload["timestamp"] = "2026-08-04T14:00:00+00:00"
        self.assertEqual([payload], apply_capacity_filters([payload]))

    def test_min_max_band_and_membership_rules(self):
        payloads = [
            self.payload("GM1", "KEEP1", reversion_zscore=-1.2),
            self.payload("GM1", "DROP1", reversion_zscore=-1.4),
            self.payload("EMA2", "KEEP2", rebound_2m_pct=0.10),
            self.payload("EMA2", "DROP2", rebound_2m_pct=0.12),
            self.payload("GT1", "KEEP3", trend_slope_pct_per_hour=1.70),
            self.payload("GT1", "DROP3", trend_slope_pct_per_hour=1.90),
            self.payload(
                "VR1",
                "KEEP4",
                universe_memberships=["HIGH_LIQUIDITY"],
            ),
            self.payload("VR1", "DROP4"),
        ]
        kept = {item["symbol"] for item in apply_capacity_filters(payloads)}
        self.assertEqual({"KEEP1", "KEEP2", "KEEP3", "KEEP4"}, kept)

    def test_rank_rule_keeps_one_best_candidate(self):
        payloads = [
            self.payload("CV1", "LOW", early_r2=0.40),
            self.payload("CV1", "HIGH", early_r2=0.90),
            self.payload("CV1", "MID", early_r2=0.65),
        ]
        kept = apply_capacity_filters(payloads)
        self.assertEqual(1, len(kept))
        self.assertEqual("HIGH", kept[0]["symbol"])

    def test_missing_required_metric_is_rejected(self):
        payload = self.payload("PD1", "MISSING")
        self.assertEqual([], apply_capacity_filters([payload]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
