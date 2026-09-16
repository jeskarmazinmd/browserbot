import importlib,inspect,unittest
from datetime import datetime,timedelta,timezone
from engine.events import MarketSnapshot,Quote
from strategies.registry import DERIVED_RUNTIME_STRATEGY_IDS,FLASH_STRATEGY_MODULES,MINUTE_STRATEGIES

IDS=("CMDMETMR1","CMDMETTR1","CMDGDR1","CMDGDU1","CMDOIL1","CMDGAS1","CMDMIN1","CMDCOP1","CMDBRD1","CMDROT1")
def mod(sid):return importlib.import_module(f"strategies.strategy_{sid.lower()}")

class Commodity10Tests(unittest.TestCase):
    def test_registered_direct_minute_paper_only(self):
        minute={x.name for x in MINUTE_STRATEGIES};self.assertEqual(len(IDS),10);self.assertEqual(set(IDS)-minute,set());self.assertEqual(set(IDS)&set(FLASH_STRATEGY_MODULES),set());self.assertEqual(set(IDS)&set(DERIVED_RUNTIME_STRATEGY_IDS),set())
        for sid in IDS:
            m=mod(sid);self.assertTrue(m.PAPER_ONLY,sid);self.assertFalse(m.LIVE_ORDER_PLACEMENT,sid);self.assertEqual(m.FORWARD_START_UTC,"2026-08-10T13:30:00+00:00");self.assertLessEqual(len(m.UNIVERSE),14);self.assertLessEqual(m.MAX_HISTORY,61)
    def test_modules_do_not_import_other_strategy_logic(self):
        for sid in IDS:
            src=inspect.getsource(mod(sid));imports=[x.strip() for x in src.splitlines() if x.strip().startswith(("from strategies","import strategies"))]
            self.assertEqual(imports,["from strategies.event_base import EventStrategy"],sid);self.assertNotIn("derived_runtime",src,sid);self.assertNotIn("snapshot_common",src,sid)
    def test_missing_optional_proxies_never_crash(self):
        start=datetime(2026,8,10,13,30,tzinfo=timezone.utc)
        for sid in IDS:
            s=mod(sid).Strategy()
            for i in range(65):
                snap=MarketSnapshot(start+timedelta(minutes=i),{"SPY":Quote(500+i*.01)},1,1,.01)
                self.assertIsInstance(s.on_snapshot(snap),list,sid)
    def test_synthetic_stream_exercises_cohort(self):
        start=datetime(2026,8,10,13,30,tzinfo=timezone.utc);strategies=[mod(x).Strategy() for x in IDS];universe=mod(IDS[0]).UNIVERSE;seen=set()
        slopes={"GLD":.06,"SLV":.045,"GDX":.018,"GDXJ":.02,"USO":.07,"UNG":.08,"XLE":.012,"OIH":.015,"XME":.025,"COPX":.05,"DBA":.02,"TLT":-.03,"UUP":-.02,"SPY":.01}
        for i in range(65):
            quotes={s:Quote(50+j+i*slopes[s]) for j,s in enumerate(universe)};snap=MarketSnapshot(start+timedelta(minutes=i),quotes,len(quotes),len(quotes),.01)
            for st in strategies:
                for ev in st.on_snapshot(snap):self.assertEqual(ev.strategy_id,st.name);self.assertEqual(ev.signal_type,"SIGNAL");seen.add(st.name)
        self.assertGreaterEqual(len(seen),5)

if __name__=="__main__":unittest.main()
