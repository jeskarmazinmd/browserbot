"""MSFLIP1: strong displayed-size imbalance flip confirmed by mid-price reversal."""
from collections import defaultdict, deque
from datetime import datetime, timezone

STRATEGY_ID="MSFLIP1";FAMILY="MICROSTRUCTURE10";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False
FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
def _r(q):
    b=float(q["bid"]);a=float(q["ask"]);x=float(q.get("bid_size") or 0);y=float(q.get("ask_size") or 0);return ((a+b)/2,(x-y)/(x+y) if x+y else 0)
class Strategy:
    name=STRATEGY_ID
    def __init__(self):self.h=defaultdict(lambda:deque(maxlen=80));self.last=None
    def evaluate(self,snapshot):
        now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc)
        for s,q in snapshot.get("quotes",{}).items():self.h[s].append(_r(q))
        if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<1200):return []
        c=[]
        for s,q in snapshot.get("quotes",{}).items():
            z=list(self.h[s]);
            if len(z)<8:continue
            before=sum(v[1] for v in z[-8:-4])/4;after=sum(v[1] for v in z[-4:])/4;move=(z[-1][0]/z[-5][0]-1)*100
            side="LONG" if before<=-.4 and after>=.4 and move>.02 else ("SHORT" if before>=.4 and after<=-.4 and move<-.02 else None)
            if side:c.append((abs(after-before)+abs(move),s,q,side,{"imbalance_before":before,"imbalance_after":after,"mid_move_20s_pct":move}))
        if not c:return []
        _,s,q,side,m=max(c);self.last=now
        return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":s,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":.32,"stop_pct":.24,"max_hold_minutes":30,"research":m,"paper_only":True,"live_order_placement":False}]
