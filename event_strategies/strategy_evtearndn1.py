from datetime import datetime, timezone
PAPER_ONLY=True; LIVE_ORDER_PLACEMENT=False; FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
class Strategy:
    name="EVTEARNDN1"
    def evaluate(self,event,quote):
        if event.get("event_type")!="EARNINGS" or event.get("direction")!="NEGATIVE": return []
        if float(event.get("magnitude") or 0)<0.05: return []
        return [_decision(self.name,event,quote,"SHORT",180,0.018,0.012)]
def _decision(s,e,q,side,hold,target,stop):
    return {"strategy_id":s,"event_id":e["event_id"],"symbol":e["symbol"],"side":side,"timestamp":datetime.now(timezone.utc).isoformat(),"published_at":e["published_at"],"source":e["source"],"entry_bid":q["bid"],"entry_ask":q["ask"],"hold_minutes":hold,"target_fraction":target,"stop_fraction":stop}
