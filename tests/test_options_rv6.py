import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from options_rv_paper_tracker import OptionsRVTracker
from options_rv_strategies import (
    strategy_rvcal1, strategy_rvcallcr1, strategy_rvcond1,
    strategy_rvdiag1, strategy_rvfly1, strategy_rvputcr1,
)


class OptionsRV6Tests(unittest.TestCase):
    def test_modules_are_independent_paper_only(self):
        modules=(strategy_rvputcr1,strategy_rvcallcr1,strategy_rvcond1,
                 strategy_rvcal1,strategy_rvdiag1,strategy_rvfly1)
        self.assertEqual(len({m.NAME for m in modules}),6)
        for module in modules:
            self.assertTrue(module.PAPER_ONLY)
            self.assertFalse(module.LIVE_ORDER_PLACEMENT)
            self.assertTrue(callable(module.evaluate))

    def test_defined_risk_credit_spread_crosses_quotes(self):
        now=datetime(2026,8,10,14,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            tracker=OptionsRVTracker(root)
            signal={"setup_id":"one","strategy_id":"TEST","defined_risk":True,
                    "max_loss_dollars":402.6,"target_return_pct":1,"max_hold_minutes":60,
                    "legs":[
                        {"symbol":"S","side":"SELL","bid":1.00,"ask":1.10},
                        {"symbol":"L","side":"BUY","bid":.40,"ask":.50},
                    ]}
            self.assertTrue(tracker.open(signal,now))
            self.assertAlmostEqual(tracker.active["one"]["opening_cash_flow"],48.7)
            tracker.update({"S":{"bid":.60,"ask":.70},"L":{"bid":.20,"ask":.30}},now+timedelta(minutes=5))
            self.assertFalse(tracker.active)
            self.assertEqual(tracker.completed,1)

    def test_rejects_naked_and_unbounded_credit(self):
        now=datetime(2026,8,10,14,tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            tracker=OptionsRVTracker(root)
            naked={"setup_id":"n","defined_risk":True,"max_loss_dollars":100,
                   "legs":[{"symbol":"S","side":"SELL","bid":1,"ask":1.1}]}
            self.assertFalse(tracker.open(naked,now))

    def test_fly_quantities_are_counted(self):
        with tempfile.TemporaryDirectory() as root:
            tracker=OptionsRVTracker(root)
            legs=[{"symbol":"A","side":"BUY","bid":2.9,"ask":3,"quantity":1},
                  {"symbol":"B","side":"SELL","bid":2,"ask":2.1,"quantity":2},
                  {"symbol":"C","side":"BUY","bid":.9,"ask":1,"quantity":1}]
            cash,sides=tracker._cash_flow(legs,True)
            self.assertEqual(sides,4)
            self.assertAlmostEqual(cash,-2.60)


if __name__=="__main__":
    unittest.main()
