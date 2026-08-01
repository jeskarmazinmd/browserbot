"""Self-contained M1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "M1"
PAPER_ONLY = True

MEDIUM_REVERSAL_CONFIGS = {
    "M1": {"lookback_minutes": 15, "min_decline_pct": 1.50, "min_rebound_from_low_pct": 0.25, "min_rebound_2m_pct": 0.10, "target_pct": 0.75, "stop_pct": 0.75},
    "M2": {"lookback_minutes": 30, "min_decline_pct": 2.25, "min_rebound_from_low_pct": 0.30, "min_rebound_2m_pct": 0.12, "target_pct": 1.00, "stop_pct": 1.00},
    "M3": {"lookback_minutes": 60, "min_decline_pct": 3.25, "min_rebound_from_low_pct": 0.40, "min_rebound_2m_pct": 0.15, "target_pct": 1.25, "stop_pct": 1.25},
}
MEDIUM_REVERSAL_MAX_LOW_AGE_MINUTES = 10
MEDIUM_REVERSAL_MAX_SINGLE_MINUTE_SHARE = 0.75
MEDIUM_REVERSAL_MIN_LOW_AGE_MINUTES = 2

def evaluate(ctx):
    sym = ctx.symbol
    work = ctx.work
    ts = ctx.timestamp
    px = ctx.current_price
    minute_et = ctx.minute_et
    prices = ctx.prices
    ret30 = ctx.return_30m_pct
    slope30 = ctx.slope_30m_pct_per_hour
    r2_30 = ctx.r2_30m
    spy_30m_return_pct = ctx.spy_30m_return_pct
    signals = []
    _independent_signal = ctx.signal_factory
    _simple_return_pct = ctx.simple_return_pct
    fit_log_slope_pct_per_hour = ctx.fit_log_slope_pct_per_hour
    _ema = ctx.ema
    _confirm_recent_volume_ratio = ctx.confirm_recent_volume_ratio
    strategy_id = "M1"
    cfg = MEDIUM_REVERSAL_CONFIGS[strategy_id]
    lookback = int(cfg["lookback_minutes"])
    if len(prices) < lookback + 1:
        return signals
    window = prices.tail(lookback + 1).reset_index(drop=True)
    start_price = float(window.iloc[0])
    low_price = float(window.min())
    low_index = int(window.idxmin())
    decline_pct = (start_price / low_price - 1.0) * 100.0 if low_price > 0 else math.nan
    low_age_minutes = (len(window) - 1) - low_index
    rebound_from_low_pct = (px / low_price - 1.0) * 100.0 if low_price > 0 else math.nan
    rebound_2m_pct = _simple_return_pct(window.iloc[-3], window.iloc[-1]) if len(window) >= 3 else math.nan
    one_minute_declines = -(window.pct_change().dropna() * 100.0)
    largest_one_minute_decline_pct = max(0.0, float(one_minute_declines.max())) if not one_minute_declines.empty else 0.0
    largest_minute_share = largest_one_minute_decline_pct / decline_pct if decline_pct > 0 else math.inf
    prior_minute_above_low = float(window.iloc[-2]) > low_price
    if (
        decline_pct >= float(cfg["min_decline_pct"])
        and MEDIUM_REVERSAL_MIN_LOW_AGE_MINUTES <= low_age_minutes <= MEDIUM_REVERSAL_MAX_LOW_AGE_MINUTES
        and rebound_from_low_pct >= float(cfg["min_rebound_from_low_pct"])
        and rebound_2m_pct >= float(cfg["min_rebound_2m_pct"])
        and prior_minute_above_low
        and largest_minute_share <= MEDIUM_REVERSAL_MAX_SINGLE_MINUTE_SHARE
    ):
        signals.append(_independent_signal(
            strategy_id, sym, ts, px, cfg["target_pct"], cfg["stop_pct"],
            f"medium_reversal_{lookback}m",
            lookback_minutes=lookback, decline_from_window_start_to_low_pct=decline_pct,
            window_start_price=start_price, window_low_price=low_price,
            low_age_minutes=low_age_minutes, rebound_from_low_pct=rebound_from_low_pct,
            rebound_2m_pct=rebound_2m_pct,
            largest_one_minute_decline_pct=largest_one_minute_decline_pct,
            largest_minute_share_of_decline=largest_minute_share,
        ))
    return signals
