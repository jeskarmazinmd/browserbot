import unittest
from research_lab.prospective_basket_tracker import analyze,prepare,simulate

def row(setup,strategy,exit_price,sequence,day="2026-08-10"):
    return {"setup_id":setup,"strategy_id":strategy,"signal_timestamp":f"{day}T14:00:00+00:00","entry_timestamp":f"{day}T14:00:00+00:00","exit_timestamp":f"{day}T14:10:00+00:00","entry_price":100,"stop_price":99,"exit_price":exit_price,"entry_sequence":sequence}

class ProspectiveBasketTrackerTests(unittest.TestCase):
    def test_forward_start_excludes_prelaunch_evidence(self):
        rows=[row("old","C2",110,0,day="2026-08-09"),row("new","C2",101,1)]
        self.assertEqual(len(prepare(rows,{"C2"},"2026-08-10T13:30:00+00:00")),1)
    def test_members_compete_for_one_cash_pool(self):
        rows=[row(str(i),"C2" if i%2 else "P",101,i) for i in range(10)]
        result=simulate(rows,["C2","P"])
        self.assertLessEqual(result["peak_deployed"],5000)
        self.assertGreater(result["skipped"],0)
        self.assertEqual(result["taken"],5)
    def test_chronological_shared_account_profit_is_independent_calculation(self):
        rows=[row("a","C2",101,0),row("b","P",99,1)]
        result=simulate(rows,["C2","P"])
        self.assertAlmostEqual(result["end_equity"],5000,places=6)
        self.assertEqual(result["taken_by_strategy"],{"C2":1,"P":1})
    def test_analysis_is_prospective_and_advisory(self):
        reports=analyze([row("a","C2",101,0),row("b","P",101,1)],[('C2','P')])
        self.assertEqual(reports[0]["completed_days"],1)
        self.assertEqual(reports[0]["role"],"ADVISORY_SHARED_CAPITAL_PAPER_EVIDENCE")

if __name__=="__main__":unittest.main()
