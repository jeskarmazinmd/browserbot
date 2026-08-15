from __future__ import annotations

import unittest

try:
    from strategies.capacity_filters import CAPACITY_FILTERS, apply_capacity_filters
except ImportError:  # Standalone artifact verification before installation.
    from capacity_filters_prospective import CAPACITY_FILTERS, apply_capacity_filters


class ProspectiveCapacityFilterTests(unittest.TestCase):
    def payload(self, strategy_id, symbol="AAA", **metrics):
        return {
            "strategy_id": strategy_id,
            "symbol": symbol,
            "timestamp": "2026-08-17T19:00:00+00:00",
            "setup_id": f"{strategy_id}|{symbol}|2026-08-17T19:00:00+00:00",
            "universe_memberships": [],
            **metrics,
        }

    def regime(self, **overrides):
        value = {
            "timestamp": "2026-08-17T19:00:00+00:00",
            "dispersion": {"bottom10_avg": -2.0, "spread": 4.0},
            "returns": {"SPY": {"5m": 0.02}},
        }
        value.update(overrides)
        return value

    def test_expected_inventory_and_ptd_filter(self):
        self.assertEqual(35, len(CAPACITY_FILTERS))

        keep = self.payload("PTD1X", "KEEP", pre_r2=0.70)
        low = self.payload("PTD1X", "LOW", pre_r2=0.60)
        missing = self.payload("PTD1X", "MISSING")

        result = apply_capacity_filters(
            [keep, low, missing],
            regime=self.regime(),
        )
        passed = {
            row["symbol"]
            for row in result
            if row["capacity_filter_passed"]
        }
        self.assertEqual({"KEEP"}, passed)

    def test_new_rules_are_inactive_before_monday(self):
        payload = self.payload("QTD1X", flash_drop_pct=0.1)
        payload["timestamp"] = "2026-08-14T19:00:00+00:00"
        self.assertEqual([payload], apply_capacity_filters([payload], regime=self.regime()))

    def test_signal_native_rules(self):
        payloads = [
            self.payload("GR1", "KEEP_GR", rejection_confirmation_from_support_pct=0.1),
            self.payload("GR1", "DROP_GR", rejection_confirmation_from_support_pct=0.2),
            self.payload("QTD1X", "KEEP_Q", flash_drop_pct=2.1),
            self.payload("QTD1X", "DROP_Q", flash_drop_pct=1.0),
        ]
        kept = apply_capacity_filters(payloads, regime=self.regime())
        passed = {row["symbol"] for row in kept if row["capacity_filter_passed"]}
        self.assertEqual({"KEEP_GR", "KEEP_Q"}, passed)

    def test_av1_combines_causal_signal_and_time_rules(self):
        keep = self.payload("AV1", "KEEP", drawdown_15m_to_5m_low_pct=0.4)
        too_large = self.payload("AV1", "LARGE", drawdown_15m_to_5m_low_pct=0.6)
        too_early = self.payload("AV1", "EARLY", drawdown_15m_to_5m_low_pct=0.4)
        too_early["timestamp"] = "2026-08-17T17:59:00+00:00"  # 13:59 ET
        kept = apply_capacity_filters([keep, too_large, too_early], regime=self.regime())
        passed = {row["symbol"] for row in kept if row["capacity_filter_passed"]}
        self.assertEqual({"KEEP"}, passed)

    def test_regime_rule_and_future_snapshot_fail_open(self):
        payload = self.payload("BO1", "BO")
        self.assertTrue(apply_capacity_filters([payload], regime=self.regime()))
        bad = self.regime(timestamp="2026-08-17T19:01:00+00:00")
        result = apply_capacity_filters([payload], regime=bad)
        self.assertEqual(1, len(result))
        self.assertTrue(result[0]["capacity_filter_passed"])
        self.assertFalse(result[0]["capacity_filter_audit"])

    def test_rejected_audit_is_deterministic(self):
        payloads = [
            self.payload("QTD1X", str(index), flash_drop_pct=0.1)
            for index in range(2000)
        ]
        first = apply_capacity_filters(payloads, regime=self.regime())
        second = apply_capacity_filters(payloads, regime=self.regime())
        first_ids = [row["setup_id"] for row in first]
        self.assertEqual(first_ids, [row["setup_id"] for row in second])
        self.assertTrue(all(row["capacity_filter_audit"] for row in first))
        self.assertGreater(len(first), 70)
        self.assertLess(len(first), 130)


if __name__ == "__main__":
    unittest.main(verbosity=2)
