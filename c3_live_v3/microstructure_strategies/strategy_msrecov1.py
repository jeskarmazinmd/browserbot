"""MSRECOV1: liquidity-withdrawal shock that reverses and replenishes."""
from collections import defaultdict, deque
from datetime import datetime, timezone

STRATEGY_ID="MSRECOV1";FAMILY="MICROSTRUCTURE10";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False
FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
def _r(q):
    b=float(q["bid"]);a=float(q["ask"]);x=float(q.get("bid_size") or 0);y=float(q.get("ask_size") or 0);return ((a+b)/2,x,y)
class Strategy:
    name=STRATEGY_ID
    def __init__(self):self.h=defaultdict(lambda:deque(maxlen=90));self.last=None
    def evaluate(self,snapshot):
        now=snapshot["timestamp"];now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00"));now=now.astimezone(timezone.utc)
        for s,q in snapshot.get("quotes",{}).items():self.h[s].append(_r(q))
        if now<datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<1200):return []
        c=[]
        for s,q in snapshot.get("quotes",{}).items():
            z=list(self.h[s]);
            if len(z)<9:continue
            old_bid=sum(x[1] for x in z[-9:-6])/3;low_bid=min(x[1] for x in z[-6:-2]);cur_bid=z[-1][1]
            old_ask=sum(x[2] for x in z[-9:-6])/3;low_ask=min(x[2] for x in z[-6:-2]);cur_ask=z[-1][2]
            bid_shock=low_bid/old_bid if old_bid>0 else 1;bid_rec=cur_bid/old_bid if old_bid>0 else 0
            ask_shock=low_ask/old_ask if old_ask>0 else 1;ask_rec=cur_ask/old_ask if old_ask>0 else 0
            move=(z[-1][0]/z[-4][0]-1)*100
            side="LONG" if bid_shock<=.35 and bid_rec>=.75 and move>.015 else ("SHORT" if ask_shock<=.35 and ask_rec>=.75 and move<-.015 else None)
            if side:c.append((max(bid_rec-bid_shock,ask_rec-ask_shock)+abs(move),s,q,side,{"bid_shock_ratio":bid_shock,"bid_recovery_ratio":bid_rec,"ask_shock_ratio":ask_shock,"ask_recovery_ratio":ask_rec,"mid_move_15s_pct":move}))
        if not c:return []
        _,s,q,side,m=max(c);self.last=now
        return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":s,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":.30,"stop_pct":.22,"max_hold_minutes":30,"research":m,"paper_only":True,"live_order_placement":False}]
