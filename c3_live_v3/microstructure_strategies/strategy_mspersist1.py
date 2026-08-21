"""MSPERSIST1: persistent one-sided displayed size plus sustained mid-price drift."""
from collections import defaultdict, deque
from datetime import datetime, timezone

STRATEGY_ID="MSPERSIST1"; FAMILY="MICROSTRUCTURE10"; PAPER_ONLY=True; LIVE_ORDER_PLACEMENT=False
FORWARD_START_UTC="2026-08-10T13:30:00+00:00"; MAX_HISTORY=120

def _r(q):
    b=float(q["bid"]);a=float(q["ask"]);x=float(q.get("bid_size") or 0);y=float(q.get("ask_size") or 0)
    return ((b+a)/2,(x-y)/(x+y) if x+y else 0)
class Strategy:
    name=STRATEGY_ID
    def __init__(self): self.h=defaultdict(lambda:deque(maxlen=MAX_HISTORY));self.last=None
    def evaluate(self,snapshot):
        now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc)
        for s,q in snapshot.get("quotes",{}).items():self.h[s].append(_r(q))
        if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<1200):return []
        c=[]
        for s,q in snapshot.get("quotes",{}).items():
            z=list(self.h[s]);
            if len(z)<13:continue
            imbs=[v[1] for v in z[-12:]];pos=sum(v>0.35 for v in imbs)/12;neg=sum(v<-0.35 for v in imbs)/12;move=(z[-1][0]/z[-13][0]-1)*100
            side="LONG" if pos>=.75 and move>.04 else ("SHORT" if neg>=.75 and move<-.04 else None)
            if side:c.append((max(pos,neg)+abs(move),s,q,side,{"positive_imbalance_fraction":pos,"negative_imbalance_fraction":neg,"mid_move_60s_pct":move}))
        if not c:return []
        _,s,q,side,m=max(c);self.last=now
        return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":s,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":.35,"stop_pct":.25,"max_hold_minutes":40,"research":m,"paper_only":True,"live_order_placement":False}]
