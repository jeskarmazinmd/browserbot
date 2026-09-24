import unittest
from datetime import datetime, timezone

from strategies import qv425_research as qv
from strategies import a_research as ar
from strategies import strategy_qv425, strategy_a


def event(ts="2026-09-25T14:00:00+00:00"):
    return {
        "timestamp": ts, "symbol": "TEST", "flash_drop_pct": 2.0,
        "pre30_return_std_pct": .25, "pre_return_pct": 2.0, "pre_r2": .8,
        "target_price": 10.5,
    }

class ResearchFamiliesTest(unittest.TestCase):
    def test_inventory_and_disjointness(self):
        self.assertGreaterEqual(len(qv.IDS), 30)
        self.assertGreaterEqual(len(ar.IDS), 30)
        self.assertEqual(len(qv.IDS), len(set(qv.IDS)))
        self.assertEqual(len(ar.IDS), len(set(ar.IDS)))
        self.assertTrue(set(qv.IDS).isdisjoint(ar.IDS))
        self.assertNotIn(strategy_qv425.STRATEGY_ID, qv.IDS)
        self.assertNotIn(strategy_a.STRATEGY_ID, ar.IDS)

    def test_controls_reproduce_parent_admission(self):
        e=event()
        self.assertEqual(qv.accepts("QV4CTL",e,10), strategy_qv425.accepts_flash(e,10))
        self.assertEqual(ar.accepts("ARCTL",e,10), strategy_a.accepts_flash(e,10))

    def test_qv_volatility_band_is_real(self):
        e=event(); self.assertTrue(qv.accepts("QV4VB608",e,10))
        e["pre30_return_std_pct"]=.20  # 10 units
        self.assertFalse(qv.accepts("QV4VB608",e,10))

    def test_a_entry_filter_is_real(self):
        e=event(); self.assertTrue(ar.accepts("ARPR150",e,10))
        e["pre_return_pct"]=1.0
        self.assertFalse(ar.accepts("ARPR150",e,10))

    def test_refresh_carries_executable_gates(self):
        q=qv.refresh("QV4XU1S50",event(),10.0)
        self.assertEqual(q["max_entry_spread_pct"],.50)
        self.assertEqual(q["min_executable_remaining_upside_pct"],1.0)
        a=ar.refresh("ARXP3U15S50",event(),10.0)
        self.assertEqual(a["min_executable_entry_price"],3.0)
        self.assertEqual(a["max_entry_spread_pct"],.50)
        self.assertEqual(a["min_executable_remaining_upside_pct"],1.5)

    def test_prospective_start_is_enforced(self):
        for module,sid in ((qv,"QV4CTL"),(ar,"ARCTL")):
            old=module.refresh(sid,event("2026-09-24T19:00:00+00:00"),10.0)
            self.assertEqual(module.validate(sid,old,0.0),(False,"before_prospective_start"))
            new=module.refresh(sid,event(),10.0)
            self.assertEqual(module.validate(sid,new,0.0),(True,None))

    def test_children_are_paper_only(self):
        for module,sid in ((qv,"QV4CTL"),(ar,"ARCTL")):
            self.assertFalse(module.config(sid)["live_order_placement"])
            row=module.refresh(sid,event(),10.0)
            self.assertTrue(row["paper_only"])
            self.assertFalse(row["live_order_placement"])
            self.assertTrue(row["experimental_child"])

if __name__ == "__main__": unittest.main()
