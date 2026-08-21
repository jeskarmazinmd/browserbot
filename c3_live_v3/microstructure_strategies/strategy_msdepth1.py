"""MSDEPTH1: cross-sectional extreme displayed-depth imbalance."""
from collections import defaultdict, deque
from datetime import datetime, timezone

STRATEGY_ID="MSDEPTH1";FAMILY="MICROSTRUCTURE10";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False
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
        rows=[]
        for s,q in snapshot.get("quotes",{}).items():
            z=list(self.h[s]);
            if len(z)<6:continue
            imb=sum(v[1] for v in z[-6:])/6;move=(z[-1][0]/z[-6][0]-1)*100;rows.append((imb,s,q,move))
        if len(rows)<12:return []
        rows.sort(); low=rows[0];high=rows[-1];pick=None
        if high[0]>=.65 and high[3]>=.02:pick=(high,"LONG")
        if low[0]<=-.65 and low[3]<=-.02 and (pick is None or abs(low[0])>abs(high[0])):pick=(low,"SHORT")
        if not pick:return []
        (imb,s,q,move),side=pick;self.last=now;m={"cross_section_extreme_imbalance":imb,"mid_move_25s_pct":move,"symbols_ranked":len(rows)}
        return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":s,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":.32,"stop_pct":.23,"max_hold_minutes":30,"research":m,"paper_only":True,"live_order_placement":False}]
