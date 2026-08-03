"""Snapshot-native EMA3: persistent 9>21>50 alignment and raw-price breakout."""
from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta
from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .nearest_miss import consider, minimum, reset
from .snapshot_common import Observation, make_signal, prices_since, trim_before, update_time_ema

STRATEGY_ID="EMA3"; PAPER_ONLY=True
EMA3_ALIGNMENT_MINUTES=5; EMA3_BREAKOUT_LOOKBACK_MINUTES=10; EMA3_BREAK_BUFFER_PCT=0.05
EMA3_FAST_SPAN=9; EMA3_MID_SPAN=21; EMA3_SLOW_SPAN=50
EMA_RESEARCH_FORWARD_START_UTC="2026-08-03T13:30:00+00:00"

@dataclass
class _State:
    observations: deque[Observation]=field(default_factory=deque)
    e9: float|None=None; e21: float|None=None; e50: float|None=None
    alignment: deque[tuple[object,bool]]=field(default_factory=deque)

class EMA3Strategy(EventStrategy):
    name=STRATEGY_ID
    def __init__(self): self._state=defaultdict(_State)
    def on_snapshot(self,snapshot:MarketSnapshot)->list[SignalEvent]:
        out=[]; reset(self)
        for symbol,q in snapshot.quotes.items():
            s=self._state[symbol]; prev=s.observations[-1] if s.observations else None
            cur=Observation(snapshot.timestamp,float(q.price),q.total_volume); s.observations.append(cur)
            trim_before(s.observations,snapshot.timestamp-timedelta(minutes=12))
            dt=(snapshot.timestamp-prev.timestamp).total_seconds() if prev else 0.0
            s.e9=update_time_ema(s.e9,cur.price,dt,9); s.e21=update_time_ema(s.e21,cur.price,dt,21); s.e50=update_time_ema(s.e50,cur.price,dt,50)
            aligned=s.e9>s.e21>s.e50
            s.alignment.append((snapshot.timestamp,aligned))
            acut=snapshot.timestamp-timedelta(minutes=EMA3_ALIGNMENT_MINUTES)
            while s.alignment and s.alignment[0][0]<acut: s.alignment.popleft()
            if not s.alignment or s.alignment[0][0]>acut or not all(v for _,v in s.alignment): continue
            prior=prices_since(s.observations,snapshot.timestamp-timedelta(minutes=EMA3_BREAKOUT_LOOKBACK_MINUTES))[:-1]
            if not prior: continue
            high=max(prior); breakout=(cur.price/high-1.0)*100.0 if high>0 else -999.0
            consider(self,symbol,snapshot.timestamp,cur.price,[minimum("breakout_pct",breakout,EMA3_BREAK_BUFFER_PCT,"%")])
            if breakout>=EMA3_BREAK_BUFFER_PCT:
                out.append(make_signal(snapshot,STRATEGY_ID,symbol,cur.price,0.90,0.60,"ema_alignment_breakout",
                    ema_9=s.e9,ema_21=s.e21,ema_50=s.e50,alignment_minutes=EMA3_ALIGNMENT_MINUTES,
                    prior_high=high,breakout_pct=breakout,forward_start_utc=EMA_RESEARCH_FORWARD_START_UTC,
                    sampling_model="continuous_time_raw_snapshots"))
        return out
