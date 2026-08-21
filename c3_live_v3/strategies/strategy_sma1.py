"""Snapshot-native SMA1 using time-weighted 20m/50m moving averages."""
from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta
from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .nearest_miss import boolean, consider, minimum, reset
from .snapshot_common import Observation, make_signal, time_weighted_mean, trim_before

STRATEGY_ID="SMA1"; PAPER_ONLY=True
SMA1_CONFIRM_MINUTES=2; SMA1_FAST_WINDOW=20; SMA1_SLOW_WINDOW=50
EMA_RESEARCH_FORWARD_START_UTC="2026-08-03T13:30:00+00:00"

@dataclass
class _State:
    observations: deque[Observation]=field(default_factory=deque)
    relation: deque[tuple[object,bool]]=field(default_factory=deque)
    crossed_at: object|None=None

class SMA1Strategy(EventStrategy):
    name=STRATEGY_ID
    def __init__(self): self._state=defaultdict(_State)
    def on_snapshot(self,snapshot:MarketSnapshot)->list[SignalEvent]:
        out=[]; reset(self)
        for symbol,q in snapshot.quotes.items():
            s=self._state[symbol]; cur=Observation(snapshot.timestamp,float(q.price),q.total_volume)
            s.observations.append(cur); trim_before(s.observations,snapshot.timestamp-timedelta(minutes=55))
            fast=time_weighted_mean(s.observations,snapshot.timestamp-timedelta(minutes=20),snapshot.timestamp)
            slow=time_weighted_mean(s.observations,snapshot.timestamp-timedelta(minutes=50),snapshot.timestamp)
            if fast is None or slow is None: continue
            above=fast>slow; prior=s.relation[-1][1] if s.relation else None
            s.relation.append((snapshot.timestamp,above))
            while s.relation and s.relation[0][0]<snapshot.timestamp-timedelta(minutes=3): s.relation.popleft()
            if prior is False and above: s.crossed_at=snapshot.timestamp
            elapsed=(snapshot.timestamp-s.crossed_at).total_seconds()/60.0 if s.crossed_at is not None else 0.0
            confirmed=s.crossed_at is not None and all(v for t,v in s.relation if t>=s.crossed_at)
            consider(self,symbol,snapshot.timestamp,cur.price,[boolean("bullish_cross_seen",s.crossed_at is not None),minimum("confirmation_minutes",elapsed,SMA1_CONFIRM_MINUTES,"minutes"),boolean("remained_above",confirmed)])
            if s.crossed_at is not None and snapshot.timestamp-s.crossed_at>=timedelta(minutes=SMA1_CONFIRM_MINUTES) and all(v for t,v in s.relation if t>=s.crossed_at):
                out.append(make_signal(snapshot,STRATEGY_ID,symbol,cur.price,0.85,0.60,"sma_20_50_bullish_crossover",
                    sma_20=fast,sma_50=slow,confirmation_minutes=SMA1_CONFIRM_MINUTES,
                    forward_start_utc=EMA_RESEARCH_FORWARD_START_UTC,sampling_model="time_weighted_raw_snapshots"))
                s.crossed_at=None
        return out
