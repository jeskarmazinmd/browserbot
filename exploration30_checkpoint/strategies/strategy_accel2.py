"""Standalone bounded prospective exploration module: ACCEL2."""
from __future__ import annotations
from collections import defaultdict, deque
from datetime import datetime, timezone
import math, statistics
from zoneinfo import ZoneInfo
from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy

STRATEGY_ID='ACCEL2'
FAMILY="EXPLORE30"
PAPER_ONLY=True
LIVE_ORDER_PLACEMENT=False
FORWARD_START_UTC="2026-08-10T13:30:00+00:00"
MODE='TREND'
PARAMS={'ret30': 0.8, 'ret5': 0.5, 'up': 0.52, 'target': 0.85, 'stop': 0.65}
UNIVERSE=('SPY', 'QQQ', 'IWM', 'DIA', 'XLK', 'XLF', 'XLE', 'XLV', 'XLY', 'XLP', 'XLI', 'XLU', 'SMH', 'IYT', 'GLD', 'SLV', 'USO', 'TLT', 'NVDA', 'AMD', 'AVGO', 'MSFT', 'AAPL', 'GOOGL', 'META', 'AMZN', 'TSLA', 'NFLX', 'ORCL', 'CRM', 'MU', 'INTC')
MAX_HISTORY=66

def _ret(prices, minutes):
    if len(prices)<minutes+1 or prices[-minutes-1]<=0: return None
    return (prices[-1]/prices[-minutes-1]-1.0)*100.0

def _event(snapshot,symbol,price,metrics):
    target=price*(1.0+float(PARAMS["target"])/100.0)
    stop=price*(1.0-float(PARAMS["stop"])/100.0)
    return SignalEvent(snapshot.timestamp,STRATEGY_ID,symbol,"SIGNAL",{
        "entry_price":price,"target_price":target,"stop_price":stop,
        "setup":f"explore30_{MODE.lower()}","paper_only":True,
        "live_order_placement":False,"forward_start_utc":FORWARD_START_UTC,
        **metrics,
    })

class Strategy(EventStrategy):
    name=STRATEGY_ID
    def __init__(self):
        self._h=defaultdict(lambda:deque(maxlen=MAX_HISTORY))

    def on_snapshot(self,snapshot:MarketSnapshot):
        for s in UNIVERSE:
            q=snapshot.quotes.get(s)
            if q is not None and q.price>0: self._h[s].append(float(q.price))
        if snapshot.timestamp.astimezone(timezone.utc)<datetime.fromisoformat(FORWARD_START_UTC): return []
        candidates=[]
        if MODE in {"REV","VOLREV"}:
            for s in UNIVERSE:
                p=list(self._h[s])
                if len(p)<34: continue
                pre=p[-34:-3]; flash=p[-4:]; start=flash[0]; low=min(flash); cur=flash[-1]
                pre_ret=(pre[-1]/pre[0]-1)*100 if pre[0]>0 else -999
                drop=(start-low)/start*100 if start>0 else 0
                rebound=(cur/low-1)*100 if low>0 else 0
                if MODE=="REV": ok=drop>=PARAMS["drop"] and rebound>=PARAMS["rebound"] and pre_ret>=PARAMS["pre"]
                else:
                    rs=[(b/a-1)*100 for a,b in zip(pre,pre[1:]) if a>0]
                    sd=statistics.pstdev(rs) if len(rs)>2 else 0
                    units=drop/sd if sd>0 else 0
                    ok=drop>=PARAMS["drop"] and rebound>=PARAMS["rebound"] and units>=PARAMS["units"]
                if ok: candidates.append((drop+rebound,s,cur,{"flash_drop_pct":drop,"rebound_pct":rebound,"pre_return_pct":pre_ret}))
        elif MODE=="TREND":
            for s in UNIVERSE:
                p=list(self._h[s]);
                if len(p)<31: continue
                r30=_ret(p,30); r5=_ret(p,5)
                up=sum(b>a for a,b in zip(p[-31:],p[-30:]))/30.0
                if r30 is not None and r5 is not None and r30>=PARAMS["ret30"] and r5>=PARAMS["ret5"] and up>=PARAMS["up"]:
                    candidates.append((r5,s,p[-1],{"return_30m_pct":r30,"return_5m_pct":r5,"up_fraction":up}))
        elif MODE=="PULL":
            for s in UNIVERSE:
                p=list(self._h[s]);
                if len(p)<31: continue
                r30=_ret(p,30); r5=_ret(p,5); r1=_ret(p,1)
                if r30 is not None and r5 is not None and r1 is not None and r30>=PARAMS["ret30"] and PARAMS["pull5"]<=r5<=0 and r1>=PARAMS["last1"]:
                    candidates.append((r30+r1,s,p[-1],{"return_30m_pct":r30,"pullback_5m_pct":r5,"rebound_1m_pct":r1}))
        elif MODE=="BREAK":
            w=int(PARAMS["window"])
            for s in UNIVERSE:
                p=list(self._h[s]);
                if len(p)<w+1: continue
                prior=p[-w-1:-1]; hi=max(prior); lo=min(prior); cur=p[-1]
                width=(hi/lo-1)*100 if lo>0 else 999
                if width<=PARAMS["range"] and cur>=hi*(1+PARAMS["buffer"]/100):
                    candidates.append(((cur/hi-1)*100,s,cur,{"prior_range_pct":width,"breakout_pct":(cur/hi-1)*100}))
        elif MODE in {"BREADTH_UP","BREADTH_REBOUND"}:
            rows=[]
            for s in UNIVERSE:
                p=list(self._h[s]); r5=_ret(p,5) if len(p)>=6 else None; r1=_ret(p,1) if len(p)>=2 else None
                if r5 is not None and r1 is not None: rows.append((s,p[-1],r5,r1))
            if len(rows)>=8:
                breadth=sum(r[2]>0 for r in rows)/len(rows)
                if MODE=="BREADTH_UP" and breadth>=PARAMS["breadth"]:
                    s,px,r5,r1=max(rows,key=lambda x:x[2]); candidates.append((r5,s,px,{"breadth":breadth,"return_5m_pct":r5}))
                elif MODE=="BREADTH_REBOUND" and breadth<=PARAMS["breadth"]:
                    rebound=[r for r in rows if r[2]<0 and r[3]>0]
                    if rebound:
                        s,px,r5,r1=min(rebound,key=lambda x:x[2]); candidates.append((-r5,s,px,{"breadth":breadth,"return_5m_pct":r5,"rebound_1m_pct":r1}))
        elif MODE in {"TIME_STRONG","TIME_REBOUND"}:
            et=snapshot.timestamp.astimezone(ZoneInfo("America/New_York")); minute=et.hour*60+et.minute
            if PARAMS["start"]<=minute<=PARAMS["end"]:
                for s in UNIVERSE:
                    p=list(self._h[s]); r30=_ret(p,30) if len(p)>=31 else None; r1=_ret(p,1) if len(p)>=2 else None
                    if r30 is None or r1 is None: continue
                    if MODE=="TIME_STRONG" and r30>=PARAMS["ret30"] and r1>0: candidates.append((r30,s,p[-1],{"return_30m_pct":r30,"return_1m_pct":r1}))
                    if MODE=="TIME_REBOUND" and r30<=PARAMS["ret30"] and r1>0: candidates.append((-r30,s,p[-1],{"return_30m_pct":r30,"return_1m_pct":r1}))
        elif MODE=="ENTROPY":
            for s in UNIVERSE:
                p=list(self._h[s]);
                if len(p)<31: continue
                r30=_ret(p,30); steps=[b>a for a,b in zip(p[-31:],p[-30:])]; positive=sum(steps)/30.0
                if r30 is not None and r30>=PARAMS["ret30"] and positive>=PARAMS["positive"]:
                    candidates.append((positive*r30,s,p[-1],{"return_30m_pct":r30,"positive_step_fraction":positive}))
        if not candidates: return []
        _,s,px,metrics=max(candidates,key=lambda x:x[0])
        return [_event(snapshot,s,px,metrics)]

def metadata(): return {"strategy_id":STRATEGY_ID,"family":FAMILY,"paper_only":True,"forward_start_utc":FORWARD_START_UTC,"bounded_symbols":len(UNIVERSE)}
