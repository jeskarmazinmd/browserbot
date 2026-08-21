"""Independent prospective EMA1-family experiment: EMA1 with volume ratio >= 1.50."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from engine.events import MarketSnapshot, SignalEvent
from strategies.event_base import EventStrategy
from .nearest_miss import boolean, consider, minimum, reset
from .snapshot_common import make_signal

STRATEGY_ID = 'EMA1V15'
DESCRIPTION = 'EMA1 with volume ratio >= 1.50'
FAMILY = "EMA1X"
PAPER_ONLY = True
FORWARD_START_UTC = '2026-08-10T13:30:00+00:00'
FAST_SPAN = 9
SLOW_SPAN = 21
MIN_VOLUME_RATIO = 1.5
TARGET_PCT = 0.75
STOP_PCT = 0.55



@dataclass
class _State:
    observations_seen: int = 0
    fast: float | None = None
    slow: float | None = None
    prior_fast: float | None = None
    prior_slow: float | None = None


class Strategy(EventStrategy):
    name = STRATEGY_ID

    def __init__(self):
        self._state: dict[str, _State] = {}

    def on_snapshot(self, snapshot: MarketSnapshot) -> list[SignalEvent]:
        signals = []
        reset(self)
        birth = datetime.fromisoformat(FORWARD_START_UTC)
        stamp = snapshot.timestamp
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        if stamp.astimezone(timezone.utc) < birth:
            return signals
        volume_provider = snapshot.metadata.get("confirm_recent_volume_ratio")

        for symbol, quote in snapshot.quotes.items():
            state = self._state.setdefault(symbol, _State())
            price = float(quote.price)
            state.prior_fast = state.fast
            state.prior_slow = state.slow
            if state.fast is None:
                state.fast = price
                state.slow = price
            else:
                fast_alpha = 2.0 / (FAST_SPAN + 1.0)
                slow_alpha = 2.0 / (SLOW_SPAN + 1.0)
                state.fast = fast_alpha * price + (1.0 - fast_alpha) * state.fast
                state.slow = slow_alpha * price + (1.0 - slow_alpha) * state.slow
            state.observations_seen += 1
            if state.observations_seen < SLOW_SPAN + 3:
                continue
            crossed = (
                state.prior_fast is not None
                and state.prior_slow is not None
                and state.prior_fast <= state.prior_slow
                and state.fast > state.slow
            )
            consider(self, symbol, snapshot.timestamp, price, [
                boolean("bullish_ema_crossover", crossed),
                boolean("volume_provider_available", callable(volume_provider)),
            ])
            if not crossed or not callable(volume_provider):
                continue
            try:
                latest_volume_ratio = volume_provider(symbol)
            except Exception:
                latest_volume_ratio = None
            consider(self, symbol, snapshot.timestamp, price, [
                minimum("volume_ratio", latest_volume_ratio, MIN_VOLUME_RATIO),
            ])
            if latest_volume_ratio is None or float(latest_volume_ratio) < MIN_VOLUME_RATIO:
                continue
            signals.append(make_signal(
                snapshot,
                STRATEGY_ID,
                symbol,
                price,
                TARGET_PCT,
                STOP_PCT,
                "ema_9_21_bullish_crossover",
                ema_9=state.fast,
                ema_21=state.slow,
                prior_ema_9=state.prior_fast,
                prior_ema_21=state.prior_slow,
                latest_volume_ratio=float(latest_volume_ratio),
                minimum_volume_ratio=MIN_VOLUME_RATIO,
                forward_start_utc=FORWARD_START_UTC,
                sampling_model="completed_minute_discrete_ema",
                volume_model="lazy_schwab_completed_minute_ratio",
            ))
        return signals
