"""Self-contained CV1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "CV1"
PAPER_ONLY = True

CV1_MIN_REBOUND_FROM_LOW_PCT = 0.25
CV1_MIN_SLOPE_IMPROVEMENT_PCT_PER_HOUR = 0.80
NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"

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
    if len(prices) >= 21:
        early_slope, early_r2 = fit_log_slope_pct_per_hour(prices.iloc[-21:-10])
        late_slope, late_r2 = fit_log_slope_pct_per_hour(prices.tail(11))
        low20 = float(prices.tail(21).min())
        rebound_low = (px / low20 - 1.0) * 100.0 if low20 > 0 else math.nan
        improvement = late_slope - early_slope
        if early_slope < 0 and improvement >= CV1_MIN_SLOPE_IMPROVEMENT_PCT_PER_HOUR and rebound_low >= CV1_MIN_REBOUND_FROM_LOW_PCT:
            signals.append(_independent_signal(
                "CV1", sym, ts, px, 0.70, 0.55, "selloff_curvature_reversal",
                early_slope_pct_per_hour=early_slope, late_slope_pct_per_hour=late_slope,
                slope_improvement_pct_per_hour=improvement, early_r2=early_r2,
                late_r2=late_r2, rebound_from_20m_low_pct=rebound_low,
                forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))
    return signals
