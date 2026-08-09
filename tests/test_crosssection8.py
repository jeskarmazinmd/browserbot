import importlib
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path

from crosssection_paper_tracker import CrossSectionPaperTracker
from crosssection_shadow_worker import STRATEGIES,_batches,fresh,normalize

class CrossSection8Tests(unittest.TestCase):
    def test_eight_independent_paper_only_strategies(self):
        self.assertEqual(len(STRATEGIES),8);self.assertEqual(len(set(STRATEGIES)),8)
        for sid in STRATEGIES:
            m=importlib.import_module(f"crosssection_strategies.strategy_{sid.lower()}")
            self.assertTrue(m.PAPER_ONLY,sid);self.assertFalse(m.LIVE_ORDER_PLACEMENT,sid)
            src=Path(m.__file__).read_text();self.assertNotIn("from crosssection_strategies",src,sid);self.assertNotIn("import crosssection_strategies",src,sid);self.assertNotIn("place_order",src,sid)

    def test_batches_respect_schwab_batch_size(self):
        groups=list(_batches([str(i) for i in range(1201)]));self.assertEqual([len(x) for x in groups],[500,500,201])

    def test_normalize_and_fresh(self):
        now=datetime(2026,8,10,14,0,tzinfo=timezone.utc);ms=int(now.timestamp()*1000)
        q=normalize("xyz",{"realtime":True,"quote":{"bidPrice":10,"askPrice":10.1,"lastPrice":10.05,"closePrice":9.8,"openPrice":10,"quoteTime":ms,"totalVolume":1000}})
        self.assertEqual(q["symbol"],"XYZ");self.assertEqual(q["close"],9.8);self.assertTrue(fresh(q,now));self.assertFalse(fresh(dict(q,realtime=False),now))

    def test_tracker_long_and_short_cross_the_spread(self):
        with tempfile.TemporaryDirectory() as root:
            t=CrossSectionPaperTracker(root,1000);now=datetime(2026,8,10,14,0,tzinfo=timezone.utc)
            common={"strategy_id":"X","timestamp":now,"target_pct":10,"stop_pct":10,"max_hold_minutes":1}
            t.open_decisions([{**common,"symbol":"AAA","side":"LONG","bid":99.9,"ask":100},{**common,"symbol":"BBB","side":"SHORT","bid":100,"ask":100.1}])
            self.assertEqual(len(t.active),2);t.update(now+timedelta(minutes=2),{"AAA":{"bid":101,"ask":101.1},"BBB":{"bid":98.9,"ask":99}})
            rows=[json.loads(x) for x in Path(root,"crosssection_paper_outcomes.jsonl").read_text().splitlines() if '"CLOSE"' in x]
            self.assertEqual(len(rows),2);self.assertAlmostEqual(rows[0]["pnl"],10);self.assertAlmostEqual(rows[1]["pnl"],10)

    def test_all_strategies_survive_broad_synthetic_stream(self):
        mods=[importlib.import_module(f"crosssection_strategies.strategy_{s.lower()}").Strategy() for s in STRATEGIES];start=datetime(2026,8,10,14,0,tzinfo=timezone.utc)
        for minute in range(25):
            quotes={}
            for i in range(120):
                symbol="SPY" if i==0 else f"S{i:03d}";base=50+i*.2;mid=base*(1+(i-60)*minute/1000000)
                quotes[symbol]={"realtime":True,"bid":mid-.01,"ask":mid+.01,"close":base*.995,"open":base,"quote_time_ms":int((start+timedelta(minutes=minute)).timestamp()*1000)}
            snap={"timestamp":start+timedelta(minutes=minute),"quotes":quotes}
            for m in mods:m.evaluate(snap)
        self.assertEqual(len(mods),8)

if __name__=="__main__":unittest.main()
