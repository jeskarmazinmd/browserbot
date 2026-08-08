import importlib,inspect,tempfile,unittest
from datetime import datetime,timedelta,timezone

from options_paper_tracker import OptionsPaperTracker

IDS=("OPTDIR1","OPTDIR2","OPTREV1","OPTBRK1","OPTIVR1","OPTSKEW1","OPTTERM1","OPTSTRAD1","OPTVERT1","OPTVERT2")

def mod(sid):return importlib.import_module(f"options_strategies.strategy_{sid.lower()}")
def contract(symbol,pc,strike,bid,ask,delta=.5,iv=20,dte=14,expiry="2026-08-24T20:00:00+00:00"):
    return {"symbol":symbol,"putCall":pc,"strikePrice":strike,"bid":bid,"ask":ask,"delta":delta if pc=="CALL" else -abs(delta),"volatility":iv,"daysToExpiration":dte,"expirationDate":expiry,"openInterest":500,"multiplier":100}

class Options10Tests(unittest.TestCase):
    def test_all_modules_fail_closed_and_are_self_contained(self):
        self.assertEqual(len(IDS),10)
        for sid in IDS:
            m=mod(sid);self.assertTrue(m.PAPER_ONLY,sid);self.assertFalse(m.LIVE_ORDER_PLACEMENT,sid);self.assertEqual(m.FORWARD_START_UTC,"2026-08-10T13:30:00+00:00")
            src=inspect.getsource(m)
            self.assertNotIn("SchwabTradeClient",src,sid);self.assertNotIn("place_order",src,sid)
            self.assertNotIn("options_strategies.strategy_",src,sid)
    def test_delayed_chain_never_generates_decision(self):
        snap={"timestamp":"2026-08-10T14:00:00+00:00","underlying":"SPY","underlyingPrice":500,"isDelayed":True,"contracts":[]}
        for sid in IDS:self.assertEqual(mod(sid).Strategy().evaluate(snap),[],sid)
    def test_paper_long_option_crosses_spread_both_ways(self):
        with tempfile.TemporaryDirectory() as root:
            t=OptionsPaperTracker(root);signal={"strategy_id":"TEST","timestamp":"2026-08-10T14:00:00+00:00","underlying":"SPY","legs":[{"symbol":"C","side":"BUY","bid":2.0,"ask":2.1,"multiplier":100}],"take_profit_pct":5,"stop_loss_pct":50,"max_hold_minutes":60}
            self.assertTrue(t.register(signal));self.assertAlmostEqual(next(iter(t.active.values()))["entry_debit"],210)
            t.update({"timestamp":"2026-08-10T14:10:00+00:00","underlying":"SPY","contracts":[{"symbol":"C","bid":2.25,"ask":2.35}]})
            self.assertEqual(t.completed,1)
            exitrow=__import__("json").loads(t.ledger.read_text().splitlines()[-1]);self.assertAlmostEqual(exitrow["pnl"],15);self.assertAlmostEqual(exitrow["return_pct"],15/210*100)
    def test_debit_spread_uses_ask_for_long_and_bid_for_short(self):
        with tempfile.TemporaryDirectory() as root:
            t=OptionsPaperTracker(root);s={"strategy_id":"V","timestamp":"2026-08-10T14:00:00+00:00","underlying":"SPY","legs":[{"symbol":"L","side":"BUY","bid":3,"ask":3.1,"multiplier":100},{"symbol":"S","side":"SELL","bid":1.0,"ask":1.1,"multiplier":100}],"take_profit_pct":20,"stop_loss_pct":20,"max_hold_minutes":60}
            self.assertTrue(t.register(s));self.assertAlmostEqual(next(iter(t.active.values()))["entry_debit"],210)
            t2=OptionsPaperTracker(root);self.assertEqual(len(t2.active),1);self.assertEqual(len(t2.seen),1)
    def test_directional_strategy_can_emit_real_option_symbol(self):
        s=mod("OPTDIR1").Strategy();start=datetime(2026,8,10,13,30,tzinfo=timezone.utc);emitted=[]
        for i in range(20):
            u=500+i*.25;snap={"timestamp":start+timedelta(minutes=i),"underlying":"SPY","underlyingPrice":u,"isDelayed":False,"contracts":[contract("SPY_CALL","CALL",round(u),2,2.05,.5),contract("SPY_PUT","PUT",round(u),2,2.05,.5)]};emitted.extend(s.evaluate(snap))
        self.assertTrue(emitted);self.assertEqual(emitted[0]["legs"][0]["symbol"],"SPY_CALL")

if __name__=="__main__":unittest.main()
