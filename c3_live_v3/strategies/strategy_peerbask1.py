"""Standalone bounded prospective coordinated exploration module: PEERBASK1."""
from __future__ import annotations
from collections import defaultdict, deque
from datetime import datetime, timezone
import math, statistics
from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy

STRATEGY_ID='PEERBASK1'
FAMILY="EXPLORE30_MULTI"
PAPER_ONLY=True
LIVE_ORDER_PLACEMENT=False
FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
MODE='PEER'
PARAMS={'breadth': 0.75, 'target': 0.6, 'stop': 0.65, 'hold': 45}
UNIVERSE=('SPY', 'QQQ', 'IWM', 'DIA', 'XLK', 'XLF', 'XLE', 'XLV', 'XLY', 'XLP', 'XLI', 'XLU', 'SMH', 'IYT', 'GLD', 'SLV', 'USO', 'TLT', 'NVDA', 'AMD', 'AVGO', 'MSFT', 'AAPL', 'GOOGL', 'META', 'AMZN', 'TSLA', 'NFLX', 'ORCL', 'CRM', 'MU', 'INTC')
SECTORS=("XLK","XLF","XLE","XLV","XLY","XLP","XLI","XLU","SMH","IYT")
TECH=("NVDA","AMD","AVGO","MSFT","AAPL","GOOGL","META","AMZN","TSLA","NFLX","ORCL","CRM","MU","INTC")
XASSET=("SPY","QQQ","IWM","TLT","GLD","SLV","USO")
MAX_HISTORY=66

def _ret(p,n):
    if len(p)<n+1 or p[-n-1]<=0:return None
    return (p[-1]/p[-n-1]-1)*100
def _returns(p): return [(b/a-1)*100 for a,b in zip(p,p[1:]) if a>0]
def _corr(a,b):
    if len(a)!=len(b) or len(a)<10:return 0.0
    ma,mb=statistics.mean(a),statistics.mean(b); da=[x-ma for x in a];db=[x-mb for x in b]
    den=math.sqrt(sum(x*x for x in da)*sum(x*x for x in db));return sum(x*y for x,y in zip(da,db))/den if den else 0.0
def _leg(s,side,w,h): return {"symbol":s,"side":side,"weight":w,"entry_price":h[s][-1]}

class Strategy(EventStrategy):
    name=STRATEGY_ID
    def __init__(self): self._h=defaultdict(lambda:deque(maxlen=MAX_HISTORY));self._last=None
    def on_snapshot(self,snapshot:MarketSnapshot):
        for s in UNIVERSE:
            q=snapshot.quotes.get(s)
            if q is not None and q.price>0:self._h[s].append(float(q.price))
        if snapshot.timestamp.astimezone(timezone.utc)<datetime.fromisoformat(FORWARD_START_UTC):return []
        if self._last is not None and (snapshot.timestamp-self._last).total_seconds()<20*60:return []
        legs=None; research={}
        if MODE in {"ROTATE","NEUTRAL","PEER","XASSET"}:
            pool=SECTORS if MODE=="ROTATE" else TECH if MODE in {"NEUTRAL","PEER"} else XASSET
            rows=[]
            for s in pool:
                r=_ret(list(self._h[s]),30)
                if r is not None:rows.append((r,s))
            rows.sort()
            if MODE=="ROTATE" and len(rows)>=6 and rows[-1][0]-rows[0][0]>=PARAMS["spread"]:
                legs=[_leg(rows[-1][1],"LONG",.5,self._h),_leg(rows[0][1],"SHORT",.5,self._h)];research={"spread_30m_pct":rows[-1][0]-rows[0][0]}
            elif MODE=="NEUTRAL" and len(rows)>=8 and rows[-1][0]-rows[0][0]>=PARAMS["spread"]:
                legs=[_leg(rows[-1][1],"LONG",.25,self._h),_leg(rows[-2][1],"LONG",.25,self._h),_leg(rows[0][1],"SHORT",.25,self._h),_leg(rows[1][1],"SHORT",.25,self._h)];research={"spread_30m_pct":rows[-1][0]-rows[0][0]}
            elif MODE=="PEER" and len(rows)>=8:
                breadth=sum(r>0 for r,_ in rows)/len(rows)
                if breadth>=PARAMS["breadth"]: chosen=rows[-3:];side="LONG"
                elif breadth<=1-PARAMS["breadth"]: chosen=rows[:3];side="SHORT"
                else: chosen=[];side="LONG"
                if chosen:legs=[_leg(s,side,1/len(chosen),self._h) for _,s in chosen];research={"breadth":breadth}
            elif MODE=="XASSET" and len(rows)>=5 and rows[-1][0]-rows[0][0]>=PARAMS["spread"]:
                a,b=rows[-1][1],rows[0][1]; pa=list(self._h[a])[-31:];pb=list(self._h[b])[-31:];c=_corr(_returns(pa),_returns(pb))
                if abs(c)>=PARAMS["corr"]:legs=[_leg(a,"LONG",.5,self._h),_leg(b,"SHORT",.5,self._h)];research={"correlation":c,"spread_30m_pct":rows[-1][0]-rows[0][0]}
        elif MODE in {"PAIR_MR","PAIR_TREND","INVERSE"}:
            pool=XASSET if MODE=="INVERSE" else SECTORS; best=None
            for i,a in enumerate(pool):
                pa=list(self._h[a])
                if len(pa)<31:continue
                for b in pool[i+1:]:
                    pb=list(self._h[b])
                    if len(pb)<31:continue
                    c=_corr(_returns(pa[-31:]),_returns(pb[-31:]));ra=_ret(pa,5);rb=_ret(pb,5)
                    if ra is None or rb is None:continue
                    if MODE!="INVERSE" and c<PARAMS["corr"]:continue
                    if MODE=="INVERSE" and c>PARAMS["corr"]:continue
                    score=abs(ra-rb)
                    if best is None or score>best[0]:best=(score,a,b,c,ra,rb)
            if best:
                score,a,b,c,ra,rb=best
                if MODE=="PAIR_TREND" and score>=PARAMS["spread"]:
                    hi,lo=(a,b) if ra>rb else (b,a);legs=[_leg(hi,"LONG",.5,self._h),_leg(lo,"SHORT",.5,self._h)]
                elif MODE=="PAIR_MR":
                    ratios=[x/y for x,y in zip(list(self._h[a])[-31:],list(self._h[b])[-31:]) if y>0]
                    sd=statistics.pstdev(ratios[:-1]) if len(ratios)>10 else 0;z=(ratios[-1]-statistics.mean(ratios[:-1]))/sd if sd>0 else 0
                    if abs(z)>=PARAMS["z"]:legs=[_leg(a,"SHORT" if z>0 else "LONG",.5,self._h),_leg(b,"LONG" if z>0 else "SHORT",.5,self._h)];research={"correlation":c,"ratio_z":z}
                elif MODE=="INVERSE" and abs(ra)>=PARAMS["move"] and abs(rb)>=PARAMS["move"] and ra*rb>0:
                    primary,other=(a,b) if abs(ra)>=abs(rb) else (b,a);pr=ra if primary==a else rb
                    legs=[_leg(primary,"SHORT" if pr>0 else "LONG",.5,self._h),_leg(other,"LONG" if pr>0 else "SHORT",.5,self._h)];research={"correlation":c,"same_direction_anomaly":True}
        elif MODE=="LEAD":
            ready=[s for s in TECH if len(self._h[s])>=33];best=None
            for leader in ready:
                lr=_returns(list(self._h[leader])[-33:]);move=lr[-1] if lr else 0; followers=[]
                if abs(move)<PARAMS["move"]:continue
                for f in ready:
                    if f==leader:continue
                    fr=_returns(list(self._h[f])[-33:]);c=_corr(lr[:-2],fr[2:])
                    if c>=PARAMS["corr"]:followers.append((c,f))
                followers.sort(reverse=True)
                if len(followers)>=2:
                    score=abs(move)*sum(x[0] for x in followers[:2])
                    if best is None or score>best[0]:best=(score,leader,move,followers[:2])
            if best:
                _,leader,move,followers=best;side="LONG" if move>0 else "SHORT";legs=[_leg(f,side,.5,self._h) for _,f in followers];research={"leader":leader,"leader_move_pct":move,"lag_correlations":dict((f,c) for c,f in followers)}
        if not legs:return []
        self._last=snapshot.timestamp
        return [SignalEvent(snapshot.timestamp,STRATEGY_ID,"+".join(x["symbol"] for x in legs),"MULTI_LEG",{
            "legs":legs,"take_profit_pct":PARAMS["target"],"stop_loss_pct":PARAMS["stop"],"max_hold_minutes":PARAMS["hold"],
            "setup":f"explore30_multi_{MODE.lower()}","paper_only":True,"live_order_placement":False,"forward_start_utc":FORWARD_START_UTC,"research":research,
        })]
def metadata():return {"strategy_id":STRATEGY_ID,"family":FAMILY,"paper_only":True,"forward_start_utc":FORWARD_START_UTC,"bounded_symbols":len(UNIVERSE)}
