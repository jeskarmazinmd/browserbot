import importlib
import unittest

from strategies import strategy_b, strategy_c3


SPECS = {
    "C3SC": ("c3", .0020, .30, .020, {}),
    "C3N20": ("c2", .0020, .30, .020, {"no_new_high_seconds": 30.0}),
    "C3N25": ("c2", .0025, .30, .020, {"no_new_high_seconds": 30.0}),
    "C3N30": ("c2", .0030, .30, .020, {"no_new_high_seconds": 30.0}),
    "C3N40": ("c2", .0040, .30, .020, {"no_new_high_seconds": 30.0}),
    "C3N50": ("c2", .0050, .30, .020, {"no_new_high_seconds": 30.0}),
    "C3N25A05": ("c2", .0025, .05, .020, {"no_new_high_seconds": 30.0}),
    "C3N25A10": ("c2", .0025, .10, .020, {"no_new_high_seconds": 30.0}),
    "C3N25A20": ("c2", .0025, .20, .020, {"no_new_high_seconds": 30.0}),
    "C3N25A50": ("c2", .0025, .50, .020, {"no_new_high_seconds": 30.0}),
    "C3N25T15": ("c2", .0025, .30, .020, {"no_new_high_seconds": 15.0}),
    "C3N25T60": ("c2", .0025, .30, .020, {"no_new_high_seconds": 60.0}),
    "C3N25S10": ("c2", .0025, .30, .010, {"no_new_high_seconds": 30.0}),
    "C3N25S15": ("c2", .0025, .30, .015, {"no_new_high_seconds": 30.0}),
    "C3N25S25": ("c2", .0025, .30, .025, {"no_new_high_seconds": 30.0}),
    "C3N25BE": (
        "c2", .0025, .30, .020,
        {"no_new_high_seconds": 30.0, "breakeven_after_activation": True},
    ),
    "C3N25W20": (
        "c2", .0025, .30, .020,
        {"no_new_high_seconds": 30.0, "pending_rebound_timeout_seconds": 1200.0},
    ),
    "C3N25W30": (
        "c2", .0025, .30, .020,
        {"no_new_high_seconds": 30.0, "pending_rebound_timeout_seconds": 1800.0},
    ),
    "C3P25": ("c1", .0025, .30, .020, {"pullback_from_high_pct": .20}),
    "C3L25": (
        "c3", .0025, .30, .020,
        {"lower_samples": 3, "min_total_decline_pct": .10},
    ),
    "C3L25Q2": (
        "c3", .0025, .30, .020,
        {"lower_samples": 2, "min_total_decline_pct": .10},
    ),
    "C3L25Q4": (
        "c3", .0025, .30, .020,
        {"lower_samples": 4, "min_total_decline_pct": .10},
    ),
    "C3L25D05": (
        "c3", .0025, .30, .020,
        {"lower_samples": 3, "min_total_decline_pct": .05},
    ),
    "C3L25D20": (
        "c3", .0025, .30, .020,
        {"lower_samples": 3, "min_total_decline_pct": .20},
    ),
}


class C3StandaloneFamilyTests(unittest.TestCase):
    def test_matrix_is_exact_and_paper_only(self):
        self.assertEqual(len(SPECS), 24)
        self.assertEqual(len(set(SPECS)), 24)

        for sid, (exit_model, rebound, activation, stop, extra) in SPECS.items():
            with self.subTest(strategy=sid):
                module=importlib.import_module(
                    f"strategies.strategy_{sid.lower()}"
                )
                cfg=module.CONFIG

                self.assertEqual(module.STRATEGY_ID, sid)
                self.assertTrue(module.PAPER_ONLY)
                self.assertFalse(cfg["live_order_placement"])
                self.assertEqual(module.EXIT_MODEL, exit_model)
                self.assertAlmostEqual(
                    cfg["rebound_confirmation_pct"], rebound
                )
                self.assertAlmostEqual(
                    cfg["activation_gain_pct"], activation
                )
                self.assertAlmostEqual(cfg["stop_loss_fraction"], stop)

                for key,value in extra.items():
                    self.assertAlmostEqual(cfg[key], value)

    def test_each_module_builds_an_independent_valid_entry(self):
        base={
            "flash_drop_pct": 1.20,
            "target_price": 101.0,
            "pre_r2": .9,
            "pre_slope_pct_per_hour": 2.0,
        }

        for sid in SPECS:
            with self.subTest(strategy=sid):
                module=importlib.import_module(
                    f"strategies.strategy_{sid.lower()}"
                )
                self.assertTrue(module.accepts_flash(base, 12.0))

                entry=module.refresh_event_for_entry(base, 100.0)
                ok,reason=module.validate_confirmed_entry(entry, .10)

                self.assertTrue(ok, reason)
                self.assertEqual(entry["strategy_id"], sid)
                self.assertEqual(entry["exit_model"], module.EXIT_MODEL)
                if "breakeven_after_activation" in module.CONFIG:
                    self.assertTrue(entry["breakeven_after_activation"])
                self.assertAlmostEqual(
                    entry["stop_price"],
                    100.0*(1.0-module.CONFIG["stop_loss_fraction"]),
                )

    def test_standalone_c3_control_matches_existing_b_entry_and_c3_exit(self):
        module=importlib.import_module("strategies.strategy_c3sc")
        cfg=module.CONFIG

        self.assertAlmostEqual(
            cfg["flash_drop_pct"],
            strategy_b.CONFIG["flash_drop_pct"],
        )
        self.assertAlmostEqual(
            cfg["rebound_confirmation_pct"],
            strategy_b.CONFIG["rebound_confirmation_pct"],
        )
        self.assertAlmostEqual(
            cfg["stop_loss_fraction"],
            strategy_c3.CONFIG["stop_loss_fraction"],
        )
        self.assertAlmostEqual(
            cfg["activation_gain_pct"],
            strategy_c3.CONFIG["activation_gain_pct"],
        )
        self.assertEqual(
            cfg["lower_samples"],
            strategy_c3.CONFIG["lower_samples"],
        )
        self.assertAlmostEqual(
            cfg["min_total_decline_pct"],
            strategy_c3.CONFIG["min_total_decline_pct"],
        )


if __name__ == "__main__":
    unittest.main()
