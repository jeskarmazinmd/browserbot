"""MSSPSHOCK1: abnormal spread widening followed by mid-price mean reversion."""
from collections import defaultdict, deque
from datetime import datetime, timezone
import statistics

STRATEGY_ID="MSSPSHOCK1";FAMILY="MICROSTRUCTURE10";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False
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
            if len(z)<18:continue
            base=statistics.median(x[1] for x in z[-18:-4]);peak=max(x[1] for x in z[-4:-1]);cur=z[-1][1];jump=peak/base if base>0 else 1;move=(z[-1][0]/z[-4][0]-1)*100
            side="LONG" if jump>=2.0 and cur<peak*.75 and move>.02 else ("SHORT" if jump>=2.0 and cur<peak*.75 and move<-.02 else None)
            if side:c.append((jump+abs(move),s,q,side,{"spread_shock_multiple":jump,"spread_now_pct":cur,"mid_recovery_pct":move}))
        if not c:return []
        _,s,q,side,m=max(c);self.last=now
        return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":s,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":.30,"stop_pct":.24,"max_hold_minutes":30,"research":m,"paper_only":True,"live_order_placement":False}]
