from datetime import datetime, timezone
PAPER_ONLY=True; LIVE_ORDER_PLACEMENT=False; FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
class Strategy:
    name="EVTGUIDUP1"
    def evaluate(self,event,quote):
        if event.get("event_type")!="GUIDANCE" or event.get("direction")!="POSITIVE": return []
        return [_d(self.name,event,quote,"LONG")]
def _d(s,e,q,side): return {"strategy_id":s,"event_id":e["event_id"],"symbol":e["symbol"],"side":side,"timestamp":datetime.now(timezone.utc).isoformat(),"published_at":e["published_at"],"source":e["source"],"entry_bid":q["bid"],"entry_ask":q["ask"],"hold_minutes":390,"target_fraction":0.025,"stop_fraction":0.015}
