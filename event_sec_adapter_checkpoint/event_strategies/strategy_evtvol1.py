from datetime import datetime,timezone
PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
class Strategy:
    name="EVTVOL1"
    def evaluate(self,event,quote):
        if not 5<=float(event.get("reaction_minutes") or 0)<=15:return []
        move=float(event.get("reaction_return") or 0);volume=float(event.get("reaction_volume") or 0)
        if abs(move)<0.005 or volume<50000:return []
        side="LONG" if move>0 else "SHORT"
        return [{"strategy_id":self.name,"event_id":event["event_id"],"symbol":event["symbol"],"side":side,"timestamp":datetime.now(timezone.utc).isoformat(),"published_at":event["published_at"],"source":event["source"],"entry_bid":quote["bid"],"entry_ask":quote["ask"],"hold_minutes":90,"target_fraction":0.012,"stop_fraction":0.009,"observed_reaction":move,"observed_volume":volume}]
