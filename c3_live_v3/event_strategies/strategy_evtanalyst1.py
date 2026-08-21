from datetime import datetime, timezone
PAPER_ONLY=True; LIVE_ORDER_PLACEMENT=False; FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
class Strategy:
    name="EVTANALYST1"
    def evaluate(self,event,quote):
        if event.get("event_type")!="ANALYST_REVISION" or event.get("direction") not in ("POSITIVE","NEGATIVE"): return []
        side="LONG" if event["direction"]=="POSITIVE" else "SHORT"
        return [{"strategy_id":self.name,"event_id":event["event_id"],"symbol":event["symbol"],"side":side,"timestamp":datetime.now(timezone.utc).isoformat(),"published_at":event["published_at"],"source":event["source"],"entry_bid":quote["bid"],"entry_ask":quote["ask"],"hold_minutes":300,"target_fraction":0.015,"stop_fraction":0.01}]
