"""Snapshot-native EMA2: rising EMA20 pullback and rebound."""
from __future__ import annotations
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta
from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .snapshot_common import Observation, make_signal, trim_before, update_time_ema, value_at_or_before

STRATEGY_ID = "EMA2"
PAPER_ONLY = True
EMA2_MAX_PULLBACK_DISTANCE_PCT = 0.35
EMA2_MIN_BOUNCE_2M_PCT = 0.10
EMA2_SPAN = 20
EMA_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"

@dataclass
class _State:
    observations: deque[Observation] = field(default_factory=deque)
    ema: float | None = None
    ema_history: deque[tuple[object, float]] = field(default_factory=deque)

class EMA2Strategy(EventStrategy):
    name = STRATEGY_ID
    def __init__(self): self._state = defaultdict(_State)

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        signals=[]
        for symbol, quote in snapshot.quotes.items():
            s=self._state[symbol]
            prev=s.observations[-1] if s.observations else None
            cur=Observation(snapshot.timestamp,float(quote.price),quote.total_volume)
            s.observations.append(cur); trim_before(s.observations,snapshot.timestamp-timedelta(minutes=25))
            dt=(snapshot.timestamp-prev.timestamp).total_seconds() if prev else 0.0
            prior_ema=s.ema
            s.ema=update_time_ema(s.ema,cur.price,dt,EMA2_SPAN)
            s.ema_history.append((snapshot.timestamp,s.ema))
            while s.ema_history and s.ema_history[0][0] < snapshot.timestamp-timedelta(minutes=5): s.ema_history.popleft()
            if prev is None or prior_ema is None: continue
            obs2=value_at_or_before(s.observations,snapshot.timestamp-timedelta(minutes=2))
            ema3=next((v for t,v in s.ema_history if t>=snapshot.timestamp-timedelta(minutes=3)),None)
            if obs2 is None or ema3 is None: continue
            ema_rising=s.ema>ema3
            prior_distance=abs(prev.price/prior_ema-1.0)*100.0 if prior_ema>0 else 999.0
            bounce=(cur.price/obs2.price-1.0)*100.0 if obs2.price>0 else -999.0
            reclaimed=prev.price<=prior_ema and cur.price>s.ema
            if ema_rising and prior_distance<=EMA2_MAX_PULLBACK_DISTANCE_PCT and bounce>=EMA2_MIN_BOUNCE_2M_PCT and reclaimed:
                signals.append(make_signal(snapshot,STRATEGY_ID,symbol,cur.price,0.75,0.50,"rising_ema20_pullback_bounce",
                    ema_20=s.ema,ema_20_change_3m_pct=(s.ema/ema3-1.0)*100.0,
                    prior_distance_from_ema_pct=prior_distance,rebound_2m_pct=bounce,
                    forward_start_utc=EMA_RESEARCH_FORWARD_START_UTC,sampling_model="continuous_time_raw_snapshots"))
        return signals
