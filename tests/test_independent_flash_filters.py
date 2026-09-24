import unittest
from datetime import datetime, timezone

import pandas as pd

from strategies.independent_flash_filters import IDS, Filters, refresh
from strategies.output_switches import output_enabled
from strategies.registry import flash_strategy_configs, flash_accepts, validate_flash_entry


class IndependentFlashFilterTests(unittest.TestCase):
    def test_all_independent_filters_have_their_own_scanner_config(self):
        configs = flash_strategy_configs()

        # Every independently runnable flash strategy must have a unique ID
        # and its own scanner configuration.  Do not hard-code the historical
        # family size: new independent research families may extend IDS.
        self.assertEqual(len(IDS), len(set(IDS)))
        self.assertTrue(set(IDS).issubset(configs))
        self.assertTrue(IDS.issubset(configs))
        self.assertTrue(all(configs[sid]["live_order_placement"] is False for sid in IDS))
        self.assertFalse(output_enabled("C3N25S10"))
        self.assertTrue(flash_accepts("C3MG_BRD50", {"flash_drop_pct": 1.2}, 5))

    def test_rebound_entry_keeps_its_own_identity_and_exit(self):
        raw = {
            "symbol": "XYZ", "flash_drop_pct": 1.2,
            "flash_start_price": 10.5, "target_price": 10.4,
        }
        self.assertTrue(flash_accepts("C4", raw, 5))
        own = refresh("C4", raw, 10.0)
        self.assertEqual(own["strategy_id"], "C4")
        self.assertEqual(own["exit_model"], "c4")
        self.assertAlmostEqual(own["stop_price"], 9.8)
        self.assertTrue(validate_flash_entry("C4", own, .2)[0])

    def test_time_and_market_rules_evaluate_own_signal(self):
        filters = Filters()
        signal = {"strategy_id": "C3N25S10NH015T1230",
                  "timestamp": datetime(2026, 9, 23, 16, 40, tzinfo=timezone.utc).isoformat(),
                  "symbol": "XYZ"}
        empty = pd.DataFrame(columns=["timestamp", "symbol", "price"])
        self.assertTrue(filters.passes(signal, empty, None, None))
        self.assertFalse(filters.passes({**signal, "strategy_id": "C3N25S10NH015T1500"}, empty, None, None))
        self.assertTrue(filters.passes({**signal, "strategy_id": "S"}, empty, -.1, .02))
        self.assertFalse(filters.passes({**signal, "strategy_id": "S"}, empty, -.3, .02))

    def test_breadth_and_density_need_no_parent_event(self):
        filters = Filters()
        at = pd.Timestamp("2026-09-23T15:30:00Z")
        rows = [
            {"timestamp": when, "symbol": f"ST{i:02}", "price": price}
            for i in range(50)
            for when, price in ((at - pd.Timedelta(minutes=6), 100.0),
                                (at - pd.Timedelta(minutes=1), 101.0))
        ]
        frame = pd.DataFrame(rows)
        own = {"strategy_id": "C3MG_BRD50", "timestamp": at.isoformat(),
               "symbol": "ST00"}
        self.assertTrue(filters.passes(own, frame, 0, 0))
        for i in range(14):
            own = {"strategy_id": "C3F_DEN5",
                   "timestamp": (at + pd.Timedelta(seconds=i)).isoformat(),
                   "symbol": f"ST{i:02}"}
            passed = filters.passes(own, frame, 0, 0)
        self.assertTrue(passed)


if __name__ == "__main__":
    unittest.main()
