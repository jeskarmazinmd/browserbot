import importlib,json,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from statarb_paper_tracker import StatArbPaperTracker
from statarb_shadow_worker import STRATEGIES,SYMBOLS,fresh,normalize

class StatArb6Tests(unittest.TestCase):
 def test_six_independent_paper_strategies(self):
  self.assertEqual(len(STRATEGIES),6);self.assertEqual(len(set(STRATEGIES)),6)
  for sid in STRATEGIES:
   m=importlib.import_module(f"statarb_strategies.strategy_{sid.lower()}");self.assertTrue(m.PAPER_ONLY,sid);self.assertFalse(m.LIVE_ORDER_PLACEMENT,sid);src=Path(m.__file__).read_text();self.assertNotIn("from statarb_strategies",src,sid);self.assertNotIn("import statarb_strategies",src,sid);self.assertNotIn("place_order",src,sid)
 def test_sector_proxy_universe_is_complete(self):
  m=importlib.import_module("statarb_strategies.strategy_stsector1");needed=set(m.GROUPS)
  for members in m.GROUPS.values():needed.update(members)
  self.assertTrue(needed<=set(SYMBOLS),needed-set(SYMBOLS))
 def test_normalize_and_fresh(self):
  now=datetime(2026,8,10,14,0,tzinfo=timezone.utc);ms=int(now.timestamp()*1000);q=normalize("xyz",{"realtime":True,"quote":{"bidPrice":100,"askPrice":100.1,"lastPrice":100.05,"quoteTime":ms}});self.assertTrue(fresh(q,now));self.assertFalse(fresh(dict(q,realtime=False),now))
 def test_group_tracker_accounts_both_spreads_and_legs(self):
  with tempfile.TemporaryDirectory() as root:
   t=StatArbPaperTracker(root,1000);now=datetime(2026,8,10,14,0,tzinfo=timezone.utc);d={"strategy_id":"X","timestamp":now,"legs":[{"symbol":"AAA","side":"LONG","bid":99.9,"ask":100,"weight":1},{"symbol":"BBB","side":"SHORT","bid":50,"ask":50.1,"weight":1}],"target_pct":10,"stop_pct":10,"max_hold_minutes":1}
   self.assertEqual(t.open_decisions([d]),1);row=next(iter(t.active.values()));self.assertEqual(row["legs"][0]["shares"],5);self.assertEqual(row["legs"][1]["shares"],10)
   t.update(now+timedelta(minutes=2),{"AAA":{"bid":101,"ask":101.1},"BBB":{"bid":48.9,"ask":49}});rows=[json.loads(x) for x in Path(root,"statarb_paper_outcomes.jsonl").read_text().splitlines()];self.assertAlmostEqual(rows[-1]["pnl"],15.0);self.assertAlmostEqual(rows[-1]["return_pct_on_gross_notional"],1.5)
 def test_all_strategies_survive_dynamic_synthetic_stream(self):
  mods=[importlib.import_module(f"statarb_strategies.strategy_{s.lower()}").Strategy() for s in STRATEGIES];start=datetime(2026,8,10,14,0,tzinfo=timezone.utc)
  for minute in range(55):
   quotes={}
   for i,s in enumerate(SYMBOLS):
    base=50+i*2;common=minute*.0004;idiosyncratic=((i%5)-2)*minute*.00002;mid=base*(1+common+idiosyncratic);quotes[s]={"realtime":True,"bid":mid-.01,"ask":mid+.01,"quote_time_ms":int((start+timedelta(minutes=minute)).timestamp()*1000)}
   snap={"timestamp":start+timedelta(minutes=minute),"quotes":quotes}
   for m in mods:m.evaluate(snap)
  self.assertEqual(len(mods),6)

if __name__=="__main__":unittest.main()
