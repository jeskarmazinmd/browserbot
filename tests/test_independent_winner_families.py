import inspect
import unittest

from strategies import strategy_c2t9, strategy_c2t35, strategy_c1t9, strategy_gt9, strategy_et29, strategy_pt325, strategy_pt325315, strategy_pmid, strategy_ht5, strategy_qmid, strategy_qv425, strategy_lt65
from strategies.registry import FLASH_STRATEGY_MODULES, MINUTE_STRATEGIES


MODULES = [strategy_c2t9, strategy_c2t35, strategy_c1t9, strategy_gt9, strategy_et29, strategy_pt325, strategy_pt325315, strategy_pmid, strategy_ht5, strategy_qmid, strategy_qv425, strategy_lt65]


def event(**updates):
    row = {
        "timestamp": "2026-08-10T16:30:00+00:00",
        "symbol": "XYZ",
        "flash_drop_pct": 1.2,
        "target_price": 8.0,
        "pre_return_pct": 1.0,
        "pre_r2": 0.7,
        "pre_slope_pct_per_hour": 1.0,
        "volume_data_status_flash": "OK",
        "flash_dollar_volume_3m": 2_000_000,
        "flash_volume_ratio": 1.2,
        "rebound_volume_ratio": 0.5,
        "pre30_return_std_pct": 0.25,
    }
    row.update(updates)
    return row


class IndependentWinnerFamilyTests(unittest.TestCase):
    def test_every_module_is_paper_only_and_registered_directly(self):
        for module in MODULES:
            self.assertTrue(module.PAPER_ONLY)
            self.assertFalse(module.CONFIG["live_order_placement"])
            self.assertIs(FLASH_STRATEGY_MODULES[module.STRATEGY_ID], module)

    def test_modules_do_not_import_or_call_parent_strategies(self):
        forbidden = (
            "strategy_a", "strategy_b", "strategy_c1", "strategy_c2",
            "strategy_e", "strategy_g", "strategy_h", "strategy_l",
            "strategy_p", "strategy_q",
        )
        for module in MODULES:
            source = inspect.getsource(module).lower()
            for name in forbidden:
                self.assertNotIn(f"import {name}", source)

    def test_forward_birth_is_enforced(self):
        module = strategy_c2t9
        raw = event(timestamp="2026-08-07T16:30:00+00:00")
        self.assertTrue(module.accepts_flash(raw, 12.0))
        confirmed = module.refresh_event_for_entry(raw, 7.8)
        ok, reason = module.validate_confirmed_entry(confirmed, 0.2)
        self.assertFalse(ok)
        self.assertEqual(reason, "before_forward_start")

    def test_price_hypotheses_are_owned_by_each_module(self):
        self.assertTrue(strategy_c2t9.accepts_flash(event(target_price=8.9), 12.0))
        self.assertFalse(strategy_c2t9.accepts_flash(event(target_price=9.1), 12.0))
        self.assertTrue(strategy_c2t35.accepts_flash(event(target_price=3.4), 12.0))
        self.assertFalse(strategy_c2t35.accepts_flash(event(target_price=3.6), 12.0))
        self.assertTrue(strategy_pt325.accepts_flash(event(target_price=3.3), 12.0))
        self.assertFalse(strategy_pt325.accepts_flash(event(target_price=3.2), 12.0))

    def test_q_and_l_hypotheses_use_their_own_inputs(self):
        self.assertTrue(strategy_qv425.accepts_flash(event(), 12.0))
        self.assertFalse(strategy_qv425.accepts_flash(event(pre30_return_std_pct=0.4), 12.0))
        raw = event(target_price=7.0)
        confirmed = strategy_lt65.refresh_event_for_entry(raw, 6.8)
        ok, reason = strategy_lt65.validate_confirmed_entry(confirmed, 0.2)
        self.assertTrue(ok, reason)
        confirmed["rebound_volume_ratio"] = 1.0
        ok, reason = strategy_lt65.validate_confirmed_entry(confirmed, 0.2)
        self.assertFalse(ok)
        self.assertEqual(reason, "rebound_volume_not_exhausted")

    def test_c_exit_models_remain_distinct(self):
        self.assertEqual(strategy_c1t9.refresh_event_for_entry(event(), 7.8)["exit_model"], "c1")
        self.assertEqual(strategy_c2t9.refresh_event_for_entry(event(), 7.8)["exit_model"], "c2")
        self.assertEqual(strategy_gt9.refresh_event_for_entry(event(), 7.8)["exit_model"], "c4")

    def test_only_ve1_and_vr1_are_parked(self):
        minute_ids = {strategy.name for strategy in MINUTE_STRATEGIES}
        self.assertNotIn("VE1", minute_ids)
        self.assertNotIn("VR1", minute_ids)


if __name__ == "__main__":
    unittest.main()
