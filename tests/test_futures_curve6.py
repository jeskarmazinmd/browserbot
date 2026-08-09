import importlib,json,sys,tempfile,types,unittest
from collections import deque
from datetime import datetime,timedelta,timezone
from pathlib import Path
try:import requests  # noqa: F401
except ModuleNotFoundError:sys.modules["requests"]=types.SimpleNamespace()
from futures_curve_paper_tracker import COMMISSION_PER_CONTRACT_SIDE,FuturesCurvePaperTracker
import futures_curve_shadow_worker as worker

IDS=("FCMES1","FCMNQ1","FCOIL1","FCOILM1","FCGOLD1","FCFX1")

def q(symbol,bid,ask,mult=5,expiration=1797570000000):return {"symbol":symbol,"realtime":True,"bid":bid,"ask":ask,"multiplier":mult,"expiration_ms":expiration,"quote_time_ms":1786136400000}

class FuturesCurveTests(unittest.TestCase):
 def test_six_independent_paper_only_modules(self):
  self.assertEqual({x.name for x in worker.load_strategies()},set(IDS))
  for sid in IDS:
   m=importlib.import_module(f"futures_curve_strategies.strategy_{sid.lower()}");self.assertTrue(m.PAPER_ONLY);self.assertFalse(m.LIVE_ORDER_PLACEMENT);text=Path(m.__file__).read_text();self.assertNotIn("place_order",text);self.assertNotIn("futures_curve_strategies.strategy_",text)
 def test_dynamic_candidates_include_known_2026_contracts(self):
  symbols=set(worker.candidate_symbols(datetime(2026,8,9,tzinfo=timezone.utc)))
  for symbol in ("/MESU26","/MESZ26","/MCLU26","/MCLV26","/MGCZ26","/MGCG27","/M6EU26","/M6EZ26"):self.assertIn(symbol,symbols)
 def test_curve_selection_sorts_by_expiration(self):
  quotes={"a":q("/MESZ26",101,102,expiration=2000),"b":q("/MESU26",100,101,expiration=1000),"c":q("/MESH27",102,103,expiration=3000)}
  self.assertEqual([x["symbol"] for x in worker.curves(quotes)["/MES"]],["/MESU26","/MESZ26","/MESH27"])
 def test_weekly_futures_session_gate(self):
  self.assertFalse(worker.futures_session(datetime(2026,8,9,20,tzinfo=timezone.utc)))
  self.assertTrue(worker.futures_session(datetime(2026,8,9,23,tzinfo=timezone.utc)))
  self.assertFalse(worker.futures_session(datetime(2026,8,10,21,30,tzinfo=timezone.utc)))
 def test_each_strategy_can_emit_after_prospective_warmup(self):
  now=datetime(2026,8,10,14,tzinfo=timezone.utc)
  roots={"FCMES1":"/MES","FCMNQ1":"/MNQ","FCOIL1":"/MCL","FCOILM1":"/MCL","FCGOLD1":"/MGC","FCFX1":"/M6E"}
  prices={"/MES":7000,"/MNQ":28000,"/MCL":75,"/MGC":4000,"/M6E":1.15};mults={"/MES":5,"/MNQ":2,"/MCL":100,"/MGC":10,"/M6E":12500}
  for sid in IDS:
   m=importlib.import_module(f"futures_curve_strategies.strategy_{sid.lower()}");s=m.Strategy();root=roots[sid];front=root+"U26";back=root+"Z26";s.contracts=(front,back);s.h.extend([1+(.03 if i%2 else -.03) for i in range(23)]);p=prices[root];spread=.01 if root!="/M6E" else .00001;rows=[q(front,p,p+spread,mults[root],1789704000000),q(back,p*1.03,p*1.03+spread,mults[root],1797570000000)];out=s.evaluate({"timestamp":now,"curves":{root:rows}});self.assertTrue(out,sid);self.assertEqual(len(out[0]["legs"]),2)

class CurvePaperTests(unittest.TestCase):
 def test_two_leg_spread_accounting_uses_multiplier_and_commission(self):
  with tempfile.TemporaryDirectory() as root:
   t=FuturesCurvePaperTracker(root);now=datetime(2026,8,10,14,tzinfo=timezone.utc);legs=[{"symbol":"/MESU26","side":"SHORT","bid":100,"ask":100.25,"multiplier":5},{"symbol":"/MESZ26","side":"LONG","bid":101,"ask":101.25,"multiplier":5}];t.open_decisions([{"strategy_id":"X","timestamp":now.isoformat(),"legs":legs,"take_profit_dollars":1,"stop_loss_dollars":100,"max_hold_minutes":60}]);t.update(now+timedelta(minutes=1),{"/MESU26":{"bid":98,"ask":98.25},"/MESZ26":{"bid":103.25,"ask":103.5}});rows=[json.loads(x) for x in t.ledger.read_text().splitlines()];close=rows[-1];self.assertEqual(close["reason"],"TARGET");self.assertAlmostEqual(close["net_pnl_dollars"],18.75-4*COMMISSION_PER_CONTRACT_SIDE)
 def test_restart_preserves_exact_contracts(self):
  with tempfile.TemporaryDirectory() as root:
   now=datetime(2026,8,10,14,tzinfo=timezone.utc);a=FuturesCurvePaperTracker(root);a.open_decisions([{"strategy_id":"X","timestamp":now.isoformat(),"legs":[{"symbol":"/MCLU26","side":"SHORT","bid":77,"ask":77.1,"multiplier":100},{"symbol":"/MCLV26","side":"LONG","bid":76,"ask":76.1,"multiplier":100}],"take_profit_dollars":100,"stop_loss_dollars":100,"max_hold_minutes":60}]);b=FuturesCurvePaperTracker(root);self.assertEqual(b.required_symbols(),["/MCLU26","/MCLV26"])

if __name__=="__main__":unittest.main()
