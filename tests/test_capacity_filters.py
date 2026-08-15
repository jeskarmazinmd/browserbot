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
        self.assertEqual(35, len(CAPACITY_FILTERS))
        self.assertEqual(35, len(set(CAPACITY_FILTERS)))
        self.assertTrue(all("kind" in rule for rule in CAPACITY_FILTERS.values()))

    def test_unconfigured_strategy_passes_through(self):
        payload = self.payload("UNCONFIGURED", "AAA")
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


    def test_new_ema_family_regime_filter_is_forward_only(self):
        regime = {
            "timestamp": "2026-08-17T13:59:00+00:00",
            "breadth": {"red_pct_5m": 35.0},
        }
        payloads = []
        for strategy_id in ("EMA1RR", "EMA1T50", "EMA1V15"):
            row = self.payload(strategy_id, f"{strategy_id}_KEEP")
            row["timestamp"] = "2026-08-17T14:00:00+00:00"
            payloads.append(row)

        kept = apply_capacity_filters(payloads, regime=regime)
        self.assertEqual(
            {"EMA1RR_KEEP", "EMA1T50_KEEP", "EMA1V15_KEEP"},
            {row["symbol"] for row in kept},
        )
        self.assertTrue(all(row["capacity_filter_passed"] for row in kept))

    def test_new_ema_family_rejects_excess_red_breadth(self):
        regime = {
            "timestamp": "2026-08-17T13:59:00+00:00",
            "breadth": {"red_pct_5m": 40.0},
        }
        payloads = []
        for strategy_id in ("EMA1RR", "EMA1T50", "EMA1V15"):
            row = self.payload(strategy_id, "DROP")
            row["timestamp"] = "2026-08-17T14:00:00+00:00"
            payloads.append(row)

        self.assertEqual([], apply_capacity_filters(payloads, regime=regime))

    def test_ptd1x_keeps_high_pre_r2_and_rejects_low_or_missing(self):
        keep = self.payload("PTD1X", "KEEP", pre_r2=0.70)
        low = self.payload("PTD1X", "DROP", pre_r2=0.60)
        missing = self.payload("PTD1X", "MISSING")
        for row in (keep, low, missing):
            row["timestamp"] = "2026-08-17T14:00:00+00:00"

        kept = apply_capacity_filters([keep, low, missing])
        self.assertEqual({"KEEP"}, {row["symbol"] for row in kept})
        self.assertTrue(kept[0]["capacity_filter_passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
