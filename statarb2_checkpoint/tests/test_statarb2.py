import importlib,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
IDS=("STCINT2","STHALF2","STHEDGE2","STLEAD2")
SYMBOLS=("SPY","QQQ","IWM","SMH","AMD","NVDA","JPM","BAC","GLD","SLV","AAPL","MSFT","XLF","XLE","IYT")
class StatArb2Tests(unittest.TestCase):
 def test_four_independent_paper_only_modules(self):
  for sid in IDS:
   m=importlib.import_module(f"statarb2_strategies.strategy_{sid.lower()}");self.assertTrue(m.PAPER_ONLY);self.assertFalse(m.LIVE_ORDER_PLACEMENT);source=Path(m.__file__).read_text();self.assertNotIn("from statarb2_strategies",source);self.assertNotIn("place_order",source)
 def test_all_modules_accept_long_dynamic_stream(self):
  modules=[importlib.import_module(f"statarb2_strategies.strategy_{sid.lower()}").Strategy() for sid in IDS];start=datetime(2026,8,10,13,30,tzinfo=timezone.utc)
  for minute in range(110):
   quotes={}
   for i,s in enumerate(SYMBOLS):
    base=40+i*3;mid=base*(1+minute*.0002+((i%4)-1.5)*minute*.00001);quotes[s]={"bid":mid-.01,"ask":mid+.01}
   for module in modules:module.evaluate({"timestamp":start+timedelta(minutes=minute),"quotes":quotes})
  self.assertEqual(len(modules),4)
if __name__=="__main__":unittest.main()
