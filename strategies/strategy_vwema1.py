"""Snapshot-native VWEMA1; preserves the original price-mean proxy semantics."""
from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta
from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .snapshot_common import Observation, make_signal, time_weighted_mean, trim_before, update_time_ema, value_at_or_before

STRATEGY_ID="VWEMA1"; PAPER_ONLY=True
VWEMA1_EMA_SPAN=20; VWEMA1_MIN_PRICE_ABOVE_VWAP_PCT=0.05; VWEMA1_MIN_RETURN_15M_PCT=0.30
EMA_RESEARCH_FORWARD_START_UTC="2026-08-03T13:30:00+00:00"

@dataclass
class _State:
    observations: deque[Observation]=field(default_factory=deque)
    ema: float|None=None
    ema_history: deque[tuple[object,float]]=field(default_factory=deque)

class VWEMA1Strategy(EventStrategy):
    name=STRATEGY_ID
    def __init__(self): self._state=defaultdict(_State)
    def on_snapshot(self,snapshot:MarketSnapshot)->list[SignalEvent]:
        out=[]
        for symbol,q in snapshot.quotes.items():
            s=self._state[symbol]; prev=s.observations[-1] if s.observations else None
            cur=Observation(snapshot.timestamp,float(q.price),q.total_volume); s.observations.append(cur)
            trim_before(s.observations,snapshot.timestamp-timedelta(minutes=35))
            dt=(snapshot.timestamp-prev.timestamp).total_seconds() if prev else 0.0
            s.ema=update_time_ema(s.ema,cur.price,dt,VWEMA1_EMA_SPAN); s.ema_history.append((snapshot.timestamp,s.ema))
            while s.ema_history and s.ema_history[0][0]<snapshot.timestamp-timedelta(minutes=5): s.ema_history.popleft()
            mean30=time_weighted_mean(s.observations,snapshot.timestamp-timedelta(minutes=30),snapshot.timestamp)
            obs15=value_at_or_before(s.observations,snapshot.timestamp-timedelta(minutes=15))
            ema3=next((v for t,v in s.ema_history if t>=snapshot.timestamp-timedelta(minutes=3)),None)
            if mean30 is None or obs15 is None or ema3 is None: continue
            above=(cur.price/mean30-1.0)*100.0 if mean30>0 else -999.0
            ret15=(cur.price/obs15.price-1.0)*100.0 if obs15.price>0 else -999.0
            if cur.price>s.ema and above>=VWEMA1_MIN_PRICE_ABOVE_VWAP_PCT and ret15>=VWEMA1_MIN_RETURN_15M_PCT and s.ema>ema3:
                out.append(make_signal(snapshot,STRATEGY_ID,symbol,cur.price,0.80,0.55,"price_above_mean_proxy_and_ema20",
                    ema_20=s.ema,rolling_price_mean_30m=mean30,distance_above_price_mean_pct=above,
                    return_15m_pct=ret15,proxy_note="time-weighted raw-price mean; not true volume-weighted VWAP",
                    forward_start_utc=EMA_RESEARCH_FORWARD_START_UTC,sampling_model="continuous_time_raw_snapshots"))
        return out
