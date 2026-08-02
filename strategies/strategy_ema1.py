"""Snapshot-native EMA1: continuous-time 9/21 EMA bullish crossover."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import timedelta

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .snapshot_common import Observation, cumulative_volume_rate, make_signal, trim_before, update_time_ema

STRATEGY_ID = "EMA1"
PAPER_ONLY = True
EMA1_FAST_SPAN = 9
EMA1_SLOW_SPAN = 21
EMA1_MIN_VOLUME_RATIO = 1.20
EMA_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"


@dataclass
class _State:
    observations: deque[Observation] = field(default_factory=deque)
    fast: float | None = None
    slow: float | None = None
    prior_fast: float | None = None
    prior_slow: float | None = None
    volume_rates: deque[tuple[object, float]] = field(default_factory=deque)


class EMA1Strategy(EventStrategy):
    name = STRATEGY_ID

    def __init__(self):
        self._state = defaultdict(_State)

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        signals = []
        for symbol, quote in snapshot.quotes.items():
            state = self._state[symbol]
            previous = state.observations[-1] if state.observations else None
            current = Observation(snapshot.timestamp, float(quote.price), quote.total_volume)
            state.observations.append(current)
            trim_before(state.observations, snapshot.timestamp - timedelta(minutes=25))

            rate = cumulative_volume_rate(previous, current)
            if rate is not None:
                state.volume_rates.append((snapshot.timestamp, rate))
            cutoff = snapshot.timestamp - timedelta(minutes=10)
            while state.volume_rates and state.volume_rates[0][0] < cutoff:
                state.volume_rates.popleft()

            dt = (snapshot.timestamp - previous.timestamp).total_seconds() if previous else 0.0
            state.prior_fast, state.prior_slow = state.fast, state.slow
            state.fast = update_time_ema(state.fast, current.price, dt, EMA1_FAST_SPAN)
            state.slow = update_time_ema(state.slow, current.price, dt, EMA1_SLOW_SPAN)

            if None in (state.prior_fast, state.prior_slow, state.fast, state.slow):
                continue
            crossed = state.prior_fast <= state.prior_slow and state.fast > state.slow
            if not crossed or rate is None or len(state.volume_rates) < 2:
                continue
            baseline_values = [value for _, value in list(state.volume_rates)[:-1]]
            baseline = sum(baseline_values) / len(baseline_values) if baseline_values else 0.0
            volume_ratio = rate / baseline if baseline > 0 else None
            if volume_ratio is None or volume_ratio < EMA1_MIN_VOLUME_RATIO:
                continue

            signals.append(make_signal(
                snapshot, STRATEGY_ID, symbol, current.price, 0.75, 0.55,
                "ema_9_21_bullish_crossover",
                ema_9=state.fast, ema_21=state.slow,
                prior_ema_9=state.prior_fast, prior_ema_21=state.prior_slow,
                latest_volume_rate_per_second=rate,
                latest_volume_ratio=volume_ratio,
                minimum_volume_ratio=EMA1_MIN_VOLUME_RATIO,
                forward_start_utc=EMA_RESEARCH_FORWARD_START_UTC,
                sampling_model="continuous_time_raw_snapshots",
            ))
        return signals
