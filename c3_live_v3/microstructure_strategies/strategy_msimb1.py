"""MSIMB1: extreme top-of-book size imbalance with price confirmation."""
from collections import defaultdict, deque
from datetime import datetime, timezone

STRATEGY_ID="MSIMB1"; FAMILY="MICROSTRUCTURE10"; PAPER_ONLY=True; LIVE_ORDER_PLACEMENT=False
FORWARD_START_UTC="2026-08-10T13:30:00+00:00"; MAX_HISTORY=90

def _row(q):
    b=float(q["bid"]); a=float(q["ask"]); bs=float(q.get("bid_size") or 0); az=float(q.get("ask_size") or 0)
    return {"mid":(b+a)/2,"bid":b,"ask":a,"imb":(bs-az)/(bs+az) if bs+az>0 else 0}

class Strategy:
    name=STRATEGY_ID
    def __init__(self): self.h=defaultdict(lambda:deque(maxlen=MAX_HISTORY)); self.last=None
    def evaluate(self,snapshot):
        now=snapshot["timestamp"]; now=now if isinstance(now,datetime) else datetime.fromisoformat(str(now).replace("Z","+00:00")); now=now.astimezone(timezone.utc)
        for s,q in snapshot.get("quotes",{}).items(): self.h[s].append(_row(q))
        if now < datetime.fromisoformat(FORWARD_START_UTC) or (self.last and (now-self.last).total_seconds()<900): return []
        out=[]
        for s,q in snapshot.get("quotes",{}).items():
            x=list(self.h[s]);
            if len(x)<7: continue
            imb=sum(r["imb"] for r in x[-4:])/4; move=(x[-1]["mid"]/x[-7]["mid"]-1)*100
            side="LONG" if imb>=0.60 and move>=0.03 else ("SHORT" if imb<=-0.60 and move<=-0.03 else None)
            if side: out.append((abs(imb)*100+abs(move),s,q,side,{"imbalance_20s":imb,"mid_move_30s_pct":move}))
        if not out:return []
        _,s,q,side,m=max(out); self.last=now
        return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"symbol":s,"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"target_pct":0.30,"stop_pct":0.22,"max_hold_minutes":30,"research":m,"paper_only":True,"live_order_placement":False}]
