"""MSVEL1: quote-mid velocity with directional top-of-book pressure."""
from collections import defaultdict, deque
from datetime import datetime, timezone

STRATEGY_ID="MSVEL1";FAMILY="MICROSTRUCTURE10";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False
FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
def _r(q):
    b=float(q["bid"]);a=float(q["ask"]);x=float(q.get("bid_size") or 0);y=float(q.get("ask_size") or 0);return ((a+b)/2,(x-y)/(x+y) if x+y else 0)
class Strategy:
    name=STRATEGY_ID
    def __init__(self):self.h=defaultdict(lambda:deque(maxlen=100));self.last=None
    def evaluate(self,snapshot):
        now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc)
        for s,q in snapshot.get("quotes",{}).items():self.h[s].append(_r(q))
        if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<900):return []
        c=[]
        for s,q in snapshot.get("quotes",{}).items():
            z=list(self.h[s]);
            if len(z)<7:continue
            mids=[x[0] for x in z[-7:]];ups=sum(b>a for a,b in zip(mids,mids[1:]));downs=sum(b<a for a,b in zip(mids,mids[1:]));move=(mids[-1]/mids[0]-1)*100;imb=sum(x[1] for x in z[-3:])/3
            side="LONG" if ups>=5 and move>=.04 and imb>.2 else ("SHORT" if downs>=5 and move<=-.04 and imb<-.2 else None)
            if side:c.append((abs(move)+abs(imb),s,q,side,{"mid_move_30s_pct":move,"up_ticks":ups,"down_ticks":downs,"recent_imbalance":imb}))
        if not c:return []
        _,s,q,side,m=max(c);self.last=now
        return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":s,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":.30,"stop_pct":.22,"max_hold_minutes":25,"research":m,"paper_only":True,"live_order_placement":False}]
