from datetime import datetime,timezone
PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
class Strategy:
    name="EVTSEC8K1"
    def evaluate(self,event,quote):
        if event.get("event_type")!="SEC_8K" or not 5<=float(event.get("reaction_minutes") or 0)<=20:return []
        move=float(event.get("reaction_return") or 0)
        if abs(move)<0.0075:return []
        side="LONG" if move>0 else "SHORT"
        return [{"strategy_id":self.name,"event_id":event["event_id"],"symbol":event["symbol"],"side":side,"timestamp":datetime.now(timezone.utc).isoformat(),"published_at":event["published_at"],"source":event["source"],"entry_bid":quote["bid"],"entry_ask":quote["ask"],"hold_minutes":240,"target_fraction":0.02,"stop_fraction":0.014,"observed_reaction":move}]
