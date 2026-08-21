"""Self-contained prospective options experiment: OPTSKEW1."""
from __future__ import annotations
from collections import defaultdict,deque
from datetime import datetime,timezone
import statistics

STRATEGY_ID='OPTSKEW1'
FAMILY="OPTIONS10"
PAPER_ONLY=True
LIVE_ORDER_PLACEMENT=False
FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
MODE='SKEW'
PARAMS={'skew': 4.0, 'dte_min': 14, 'dte_max': 35, 'tp': 22, 'sl': 18, 'hold': 180}
MAX_HISTORY=66

def _ret(h,n):
    return None if len(h)<n+1 or h[-n-1]<=0 else (h[-1]/h[-n-1]-1)*100

def _liquid(c):
    b=float(c.get("bid") or 0);a=float(c.get("ask") or 0);m=(a+b)/2 if a>0 and b>0 else 0
    spread=(a-b)/m*100 if m>0 else 999
    return b>0 and a>=b and spread<=12 and int(c.get("openInterest") or 0)>=50

def _contracts(snapshot,putcall=None,dmin=0,dmax=999):
    out=[]
    for c in snapshot.get("contracts",[]):
        if putcall and str(c.get("putCall",""))!=putcall:continue
        d=int(c.get("daysToExpiration") or -1)
        if dmin<=d<=dmax and _liquid(c):out.append(c)
    return out

def _atm(items,u):
    return min(items,key=lambda c:abs(float(c.get("strikePrice") or 0)-u)) if items else None

def _delta(items,lo=.35,hi=.65):
    eligible=[c for c in items if lo<=abs(float(c.get("delta") or 0))<=hi]
    return min(eligible,key=lambda c:abs(abs(float(c.get("delta") or 0))-.5)) if eligible else None

def _leg(c,side):
    return {"symbol":c["symbol"],"side":side,"bid":float(c["bid"]),"ask":float(c["ask"]),"multiplier":int(c.get("multiplier") or 100),"strike":float(c.get("strikePrice") or 0),"expiration":c.get("expirationDate"),"put_call":c.get("putCall")}

class Strategy:
    name=STRATEGY_ID
    def __init__(self):
        self._under=defaultdict(lambda:deque(maxlen=MAX_HISTORY));self._iv=defaultdict(lambda:deque(maxlen=24));self._last=None
    def evaluate(self,snapshot):
        now=snapshot["timestamp"]
        if isinstance(now,str):now=datetime.fromisoformat(now.replace("Z","+00:00"))
        if now.astimezone(timezone.utc)<datetime.fromisoformat(FORWARD_START_UTC):return []
        if snapshot.get("isDelayed") is True:return []
        underlying=str(snapshot["underlying"]);u=float(snapshot["underlyingPrice"])
        self._under[underlying].append(u);h=list(self._under[underlying])
        if self._last and (now-self._last).total_seconds()<20*60:return []
        legs=None;research={"underlying":underlying,"underlying_price":u,"mode":MODE}
        dmin=int(PARAMS.get("dte_min",0));dmax=int(PARAMS.get("dte_max",999))
        calls=_contracts(snapshot,"CALL",dmin,dmax);puts=_contracts(snapshot,"PUT",dmin,dmax)
        if MODE in {"DIR","VERT"}:
            n=int(PARAMS["lookback"]);r=_ret(h,n)
            if r is None or abs(r)<PARAMS["move"]:return []
            side="CALL" if r>0 else "PUT";items=calls if side=="CALL" else puts
            c=_delta(items,float(PARAMS.get("delta_min",.35)),float(PARAMS.get("delta_max",.65)))
            if not c:return []
            if MODE=="DIR":legs=[_leg(c,"BUY")]
            else:
                strike=float(c["strikePrice"]);width=float(PARAMS["width"]);target=strike+width if side=="CALL" else strike-width
                same=[x for x in items if x.get("expirationDate")==c.get("expirationDate")]
                hedge=min(same,key=lambda x:abs(float(x["strikePrice"])-target)) if same else None
                if not hedge or hedge["symbol"]==c["symbol"]:return []
                legs=[_leg(c,"BUY"),_leg(hedge,"SELL")]
            research["underlying_return_pct"]=r
        elif MODE=="REV":
            n=int(PARAMS["lookback"])
            if len(h)<n+2:return []
            r=_ret(h,n);r1=_ret(h,1)
            if r is None or r1 is None or abs(r)<PARAMS["move"] or r*r1>=0 or abs(r1)<PARAMS["rebound"]:return []
            items=calls if r<0 else puts;c=_delta(items)
            if not c:return []
            legs=[_leg(c,"BUY")];research.update({"prior_move_pct":r,"rebound_pct":r1})
        elif MODE=="BREAK":
            n=int(PARAMS["lookback"])
            if len(h)<n+1:return []
            prior=h[-n-1:-1];hi=max(prior);lo=min(prior)
            if u>=hi*(1+PARAMS["move"]/100):items=calls;direction="UP"
            elif u<=lo*(1-PARAMS["move"]/100):items=puts;direction="DOWN"
            else:return []
            c=_delta(items)
            if not c:return []
            legs=[_leg(c,"BUY")];research["breakout_direction"]=direction
        elif MODE=="IVREV":
            both=calls+puts;c=_atm(both,u)
            if not c:return []
            key=(underlying,c.get("expirationDate"),c.get("putCall"));iv=float(c.get("volatility") or 0);hist=self._iv[key]
            if len(hist)>=PARAMS["iv_window"]:
                base=list(hist)[-int(PARAMS["iv_window"]):];sd=statistics.pstdev(base);z=(iv-statistics.mean(base))/sd if sd>0 else 0
            else:z=0
            hist.append(iv)
            # Only test long premium after unusually low IV; high-IV short premium is deliberately excluded.
            if z>-PARAMS["iv_z"]:return []
            pc="CALL" if (_ret(h,5) or 0)>=0 else "PUT";c=_atm(calls if pc=="CALL" else puts,u)
            if not c:return []
            legs=[_leg(c,"BUY")];research["iv_z"]=z
        elif MODE=="SKEW":
            c=_delta(calls,.20,.40);p=_delta(puts,.20,.40)
            if not c or not p:return []
            gap=float(p.get("volatility") or 0)-float(c.get("volatility") or 0)
            if abs(gap)<PARAMS["skew"]:return []
            # Buy the relatively cheap wing, never naked-short the expensive wing.
            chosen=c if gap>0 else p;legs=[_leg(chosen,"BUY")];research["put_minus_call_iv"]=gap
        elif MODE=="TERM":
            near=_contracts(snapshot,None,PARAMS["near_min"],PARAMS["near_max"]);far=_contracts(snapshot,None,PARAMS["far_min"],PARAMS["far_max"])
            n=_atm(near,u);f=_atm(far,u)
            if not n or not f:return []
            gap=float(n.get("volatility") or 0)-float(f.get("volatility") or 0)
            if abs(gap)<PARAMS["term_gap"]:return []
            chosen=f if gap>0 else n;legs=[_leg(chosen,"BUY")];research["near_minus_far_iv"]=gap
        elif MODE=="STRADDLE":
            r=_ret(h,5)
            if r is None or abs(r)<PARAMS["rv_move"]:return []
            c=_atm(calls,u);p=_atm(puts,u)
            if not c or not p or c.get("expirationDate")!=p.get("expirationDate"):return []
            legs=[_leg(c,"BUY"),_leg(p,"BUY")];research["underlying_5m_move_pct"]=r
        if not legs:return []
        self._last=now
        return [{"strategy_id":STRATEGY_ID,"timestamp":now.isoformat(),"underlying":underlying,"legs":legs,"take_profit_pct":PARAMS["tp"],"stop_loss_pct":PARAMS["sl"],"max_hold_minutes":PARAMS["hold"],"paper_only":True,"live_order_placement":False,"research":research}]
