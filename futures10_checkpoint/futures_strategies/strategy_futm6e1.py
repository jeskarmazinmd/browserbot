"""Self-contained prospective micro-futures experiment: FUTM6E1."""
from __future__ import annotations
from collections import defaultdict,deque
from datetime import datetime,timezone
import math,statistics
STRATEGY_ID='FUTM6E1';FAMILY="FUTURES10";PAPER_ONLY=True;LIVE_ORDER_PLACEMENT=False;FORWARD_START_UTC="2026-08-09T22:00:00+00:00";MODE='TREND';PARAMS={'root': '/M6E', 'lookback': 30, 'move': 0.1, 'tp': 45, 'sl': 35, 'hold': 180};MAX_HISTORY=61

def _ret(h,n):return None if len(h)<n+1 or h[-n-1]<=0 else (h[-1]/h[-n-1]-1)*100
def _leg(q,side):return {"root":q["root"],"symbol":q["contractSymbol"],"side":side,"bid":float(q["bid"]),"ask":float(q["ask"]),"multiplier":float(q["multiplier"]),"expiration":q.get("expiration")}

class Strategy:
    name=STRATEGY_ID
    def __init__(self):self._h=defaultdict(lambda:deque(maxlen=MAX_HISTORY));self._active={};self._last=None
    def _push(self,root,q):
        contract=q["contractSymbol"]
        if self._active.get(root)!=contract:self._h[root].clear();self._active[root]=contract
        self._h[root].append((float(q["bid"])+float(q["ask"]))/2)
    def evaluate(self,snapshot):
        now=snapshot["timestamp"]
        if isinstance(now,str):now=datetime.fromisoformat(now.replace("Z","+00:00"))
        if now.astimezone(timezone.utc)<datetime.fromisoformat(FORWARD_START_UTC):return []
        quotes=snapshot.get("roots",{})
        for root,q in quotes.items():
            if q.get("realtime") is True and float(q.get("bid") or 0)>0 and float(q.get("ask") or 0)>=float(q.get("bid") or 0):self._push(root,q)
        if self._last and (now-self._last).total_seconds()<20*60:return []
        legs=None;research={"mode":MODE}
        if MODE in {"TREND","REV"}:
            root=PARAMS["root"];q=quotes.get(root);h=list(self._h[root]);n=int(PARAMS["lookback"])
            if not q or q.get("realtime") is not True:return []
            r=_ret(h,n)
            if r is None:return []
            if MODE=="TREND" and abs(r)>=PARAMS["move"]:legs=[_leg(q,"LONG" if r>0 else "SHORT")];research["return_pct"]=r
            elif MODE=="REV":
                r1=_ret(h,1)
                if r1 is not None and abs(r)>=PARAMS["move"] and r*r1<0 and abs(r1)>=PARAMS["rebound"]:legs=[_leg(q,"LONG" if r<0 else "SHORT")];research.update({"prior_return_pct":r,"rebound_pct":r1})
        elif MODE=="PAIR":
            a,b=PARAMS["a"],PARAMS["b"];qa,qb=quotes.get(a),quotes.get(b);ha,hb=list(self._h[a]),list(self._h[b]);n=int(PARAMS["lookback"])
            if not qa or not qb or len(ha)<n+1 or len(hb)<n+1:return []
            ratios=[math.log(x/y) for x,y in zip(ha[-n-1:],hb[-n-1:]) if x>0 and y>0]
            sd=statistics.pstdev(ratios[:-1]) if len(ratios)==n+1 else 0;z=(ratios[-1]-statistics.mean(ratios[:-1]))/sd if sd>0 else 0
            if abs(z)>=PARAMS["z"]:legs=[_leg(qa,"SHORT" if z>0 else "LONG"),_leg(qb,"LONG" if z>0 else "SHORT")];research["ratio_z"]=z
        elif MODE=="DIVERGE":
            a,b=PARAMS["a"],PARAMS["b"];qa,qb=quotes.get(a),quotes.get(b);ra,rb=_ret(list(self._h[a]),PARAMS["lookback"]),_ret(list(self._h[b]),PARAMS["lookback"])
            if qa and qb and ra is not None and rb is not None and abs(ra-rb)>=PARAMS["spread"]:legs=[_leg(qa,"LONG" if ra>rb else "SHORT"),_leg(qb,"SHORT" if ra>rb else "LONG")];research.update({"a_return_pct":ra,"b_return_pct":rb,"spread_pct":ra-rb})
        if not legs:return []
        self._last=now;return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"legs":legs,"take_profit_dollars":PARAMS["tp"],"stop_loss_dollars":PARAMS["sl"],"max_hold_minutes":PARAMS["hold"],"paper_only":True,"live_order_placement":False,"research":research}]
