"""Self-contained bounded prospective commodity/macro ETF experiment: CMDMETTR1."""
from __future__ import annotations
from collections import defaultdict,deque
from datetime import datetime,timezone
import math,statistics
from engine.events import MarketSnapshot,SignalEvent
from strategies.event_base import EventStrategy

STRATEGY_ID='CMDMETTR1'
FAMILY="COMMODITY10"
PAPER_ONLY=True
LIVE_ORDER_PLACEMENT=False
FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
MODE='PAIR_TREND'
PARAMS={'a': 'GLD', 'b': 'SLV', 'lookback': 30, 'minret': 0.45, 'target': 0.9, 'stop': 0.65}
UNIVERSE=("GLD","SLV","GDX","GDXJ","USO","UNG","XLE","OIH","XME","COPX","DBA","TLT","UUP","SPY")
MAX_HISTORY=61

def _ret(h,n):return None if len(h)<n+1 or h[-n-1]<=0 else (h[-1]/h[-n-1]-1)*100
def _corr(a,b):
    if len(a)!=len(b) or len(a)<10:return 0
    ma,mb=statistics.mean(a),statistics.mean(b);da=[x-ma for x in a];db=[x-mb for x in b];den=math.sqrt(sum(x*x for x in da)*sum(x*x for x in db));return sum(x*y for x,y in zip(da,db))/den if den else 0
def _event(snapshot,symbol,price,research):
    return SignalEvent(snapshot.timestamp,STRATEGY_ID,symbol,"SIGNAL",{"entry_price":price,"target_price":price*(1+PARAMS["target"]/100),"stop_price":price*(1-PARAMS["stop"]/100),"setup":f"commodity10_{MODE.lower()}","paper_only":True,"live_order_placement":False,"forward_start_utc":FORWARD_START_UTC,"research":research})

class Strategy(EventStrategy):
    name=STRATEGY_ID
    def __init__(self):self._h=defaultdict(lambda:deque(maxlen=MAX_HISTORY));self._last=None
    def on_snapshot(self,snapshot:MarketSnapshot):
        for s in UNIVERSE:
            q=snapshot.quotes.get(s)
            if q is not None and q.price>0:self._h[s].append(float(q.price))
        if snapshot.timestamp.astimezone(timezone.utc)<datetime.fromisoformat(FORWARD_START_UTC):return []
        if self._last and (snapshot.timestamp-self._last).total_seconds()<20*60:return []
        chosen=None;research={"mode":MODE}
        if MODE=="PAIR_MR":
            a,b=PARAMS["a"],PARAMS["b"];n=int(PARAMS["lookback"]);ha,hb=list(self._h[a]),list(self._h[b])
            if len(ha)>=n+1 and len(hb)>=n+1:
                ra=[math.log(x/y) for x,y in zip(ha[-n-1:],hb[-n-1:]) if x>0 and y>0]
                if len(ra)==n+1:
                    sd=statistics.pstdev(ra[:-1]);z=(ra[-1]-statistics.mean(ra[:-1]))/sd if sd>0 else 0
                    if abs(z)>=PARAMS["z"]:chosen=b if z>0 else a;research["ratio_z"]=z
        elif MODE=="PAIR_TREND":
            a,b=PARAMS["a"],PARAMS["b"];n=int(PARAMS["lookback"]);ra,rb=_ret(list(self._h[a]),n),_ret(list(self._h[b]),n)
            if ra is not None and rb is not None and ra>=PARAMS["minret"] and rb>=PARAMS["minret"]:chosen=a if ra>=rb else b;research.update({"a_return":ra,"b_return":rb})
        elif MODE=="GOLD_RATE":
            n=int(PARAMS["lookback"]);g,t=_ret(list(self._h["GLD"]),n),_ret(list(self._h["TLT"]),n)
            if g is not None and t is not None and g>=PARAMS["gold"] and t<=PARAMS["tlt"]:chosen="GLD";research.update({"gold_return":g,"tlt_return":t})
        elif MODE=="GOLD_USD":
            n=int(PARAMS["lookback"]);g,u=_ret(list(self._h["GLD"]),n),_ret(list(self._h["UUP"]),n)
            if g is not None and u is not None and g>=PARAMS["gold"] and u<=PARAMS["uup"]:chosen="GLD";research.update({"gold_return":g,"uup_return":u})
        elif MODE=="LEAD":
            n=int(PARAMS["lookback"]);a,b=PARAMS["leader"],PARAMS["follower"];ra,rb=_ret(list(self._h[a]),n),_ret(list(self._h[b]),n)
            if ra is not None and rb is not None and ra>=PARAMS["lead"] and 0<=rb<=PARAMS["lagmax"]:chosen=b;research.update({"leader":a,"leader_return":ra,"follower_return":rb})
        elif MODE=="CONFIRM":
            n=int(PARAMS["lookback"]);a,b=PARAMS["a"],PARAMS["b"];ra,rb=_ret(list(self._h[a]),n),_ret(list(self._h[b]),n)
            if ra is not None and rb is not None and ra>=PARAMS["aret"] and rb>=PARAMS["bret"]:chosen=a;research.update({"a_return":ra,"b_return":rb})
        elif MODE in {"BREADTH","ROTATE"}:
            n=int(PARAMS["lookback"]);pool=("GLD","SLV","GDX","USO","UNG","XLE","XME","COPX","DBA");rows=[]
            for s in pool:
                r=_ret(list(self._h[s]),n)
                if r is not None:rows.append((r,s))
            if MODE=="BREADTH" and len(rows)>=5:
                breadth=sum(r>0 for r,_ in rows)/len(rows);best=max(rows)
                if breadth>=PARAMS["breadth"] and best[0]>=PARAMS["minret"]:chosen=best[1];research.update({"breadth":breadth,"best_return":best[0]})
            elif MODE=="ROTATE" and len(rows)>=4:
                best=max(rows)
                if best[0]>=PARAMS["minret"]:chosen=best[1];research["best_return"]=best[0]
        if not chosen or not self._h[chosen]:return []
        self._last=snapshot.timestamp;return [_event(snapshot,chosen,self._h[chosen][-1],research)]

def metadata():return {"strategy_id":STRATEGY_ID,"family":FAMILY,"paper_only":True,"forward_start_utc":FORWARD_START_UTC,"bounded_symbols":len(UNIVERSE)}
