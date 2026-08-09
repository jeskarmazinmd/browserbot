"""MSSPCOMP1: spread compression followed by directional mid-price release."""
from collections import defaultdict, deque
from datetime import datetime, timezone
import statistics

STRATEGY_ID="MSSPCOMP1";FAMILY="MICROSTRUCTURE10";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False
FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
def _r(q):
    b=float(q["bid"]);a=float(q["ask"]);m=(a+b)/2;return (m,(a-b)/m*100 if m else 0)
class Strategy:
    name=STRATEGY_ID
    def __init__(self):self.h=defaultdict(lambda:deque(maxlen=120));self.last=None
    def evaluate(self,snapshot):
        now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc)
        for s,q in snapshot.get("quotes",{}).items():self.h[s].append(_r(q))
        if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<1200):return []
        c=[]
        for s,q in snapshot.get("quotes",{}).items():
            z=list(self.h[s]);
            if len(z)<15:continue
            prior=statistics.median(x[1] for x in z[-15:-3]);cur=sum(x[1] for x in z[-3:])/3;ratio=cur/prior if prior>0 else 1;move=(z[-1][0]/z[-4][0]-1)*100
            side="LONG" if ratio<=.55 and move>=.025 else ("SHORT" if ratio<=.55 and move<=-.025 else None)
            if side:c.append(((1-ratio)+abs(move),s,q,side,{"spread_compression_ratio":ratio,"spread_pct":cur,"mid_move_15s_pct":move}))
        if not c:return []
        _,s,q,side,m=max(c);self.last=now
        return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":s,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":.28,"stop_pct":.20,"max_hold_minutes":25,"research":m,"paper_only":True,"live_order_placement":False}]
