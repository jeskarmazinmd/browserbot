"""MSASKPULL1: abrupt displayed ask-size withdrawal with upside confirmation."""
from collections import defaultdict, deque
from datetime import datetime, timezone
import statistics

STRATEGY_ID="MSASKPULL1";FAMILY="MICROSTRUCTURE10";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False
FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
class Strategy:
    name=STRATEGY_ID
    def __init__(self):self.h=defaultdict(lambda:deque(maxlen=90));self.last=None
    def evaluate(self,snapshot):
        now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc)
        for s,q in snapshot.get("quotes",{}).items():
            b=float(q["bid"]);a=float(q["ask"]);self.h[s].append(((a+b)/2,float(q.get("ask_size") or 0)))
        if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<1200):return []
        c=[]
        for s,q in snapshot.get("quotes",{}).items():
            z=list(self.h[s]);
            if len(z)<10:continue
            base=statistics.median(v[1] for v in z[-10:-2]);cur=z[-1][1];ratio=cur/base if base>0 else 1;move=(z[-1][0]/z[-4][0]-1)*100
            if ratio<=.30 and move>=.025:c.append(((1-ratio)+abs(move),s,q,{"ask_size_vs_recent_median":ratio,"mid_move_15s_pct":move}))
        if not c:return []
        _,s,q,m=max(c);self.last=now
        return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":s,"side":"LONG","bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":.30,"stop_pct":.22,"max_hold_minutes":25,"research":m,"paper_only":True,"live_order_placement":False}]
