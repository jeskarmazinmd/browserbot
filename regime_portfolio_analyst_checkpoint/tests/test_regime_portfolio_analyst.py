import json,tempfile,unittest
from pathlib import Path
from research_lab.regime_portfolio_analyst import lagged_regimes,load_close_regimes,rank_baskets

class RegimePortfolioAnalystTests(unittest.TestCase):
    def test_regime_is_strictly_lagged(self):
        self.assertEqual(lagged_regimes(["2026-08-06","2026-08-07"],{"2026-08-06":"UP","2026-08-07":"DOWN"}),{"2026-08-07":"UP"})
    def test_latest_good_snapshot_defines_close_regime(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/"r.jsonl";rows=[
                {"timestamp":"2026-08-06T18:00:00+00:00","data_quality":{"quality":"GOOD"},"labels":{"direction":"UP","breadth":"MIXED"},"trend":{"classification":"UPTREND"},"volatility":{"classification":"LOW"}},
                {"timestamp":"2026-08-06T19:00:00+00:00","data_quality":{"quality":"GOOD"},"labels":{"direction":"FLAT","breadth":"MIXED"},"trend":{"classification":"CHOP"},"volatility":{"classification":"NORMAL"}}]
            p.write_text("\n".join(json.dumps(x) for x in rows)+"\n")
            self.assertEqual(load_close_regimes(p)["2026-08-06"],"FLAT|CHOP|NORMAL|MIXED")
    def test_diversified_candidate_can_rank_and_is_advisory(self):
        capital={}
        for i,day in enumerate(("2026-08-06","2026-08-07","2026-08-08","2026-08-09")):
            capital[day]={"A":{"return_pct":1 if i%2==0 else -0.2,"signals":30},"B":{"return_pct":-0.1 if i%2==0 else 1,"signals":30},"BAD":{"return_pct":-1,"signals":30}}
        regimes={"2026-08-05":"R","2026-08-06":"R","2026-08-07":"R","2026-08-08":"R","2026-08-09":"R"}
        report=rank_baskets(capital,regimes,max_size=2,candidate_limit=3,min_days=3)
        self.assertEqual(report["status"],"ADVISORY_ONLY")
        self.assertTrue(report["recommendations"])
        self.assertIn("causal_rule",report)
    def test_insufficient_evidence_is_explicit(self):
        report=rank_baskets({"2026-08-06":{"A":{"return_pct":1,"signals":30}}},{})
        self.assertEqual(report["status"],"INSUFFICIENT_EVIDENCE")

if __name__=="__main__":unittest.main()
