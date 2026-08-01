"""Self-contained BO1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "BO1"
PAPER_ONLY = True

BO1_BREAK_BUFFER_PCT = 0.10
BO1_LOOKBACK_MINUTES = 10
BO1_MAX_RANGE_PCT = 0.75

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
    if len(prices) >= BO1_LOOKBACK_MINUTES + 2:
        prior = prices.iloc[-(BO1_LOOKBACK_MINUTES + 1):-1]
        prior_high = float(prior.max()); prior_low = float(prior.min())
        range_pct = (prior_high / prior_low - 1.0) * 100.0 if prior_low > 0 else math.nan
        breakout_pct = (px / prior_high - 1.0) * 100.0 if prior_high > 0 else math.nan
        if range_pct <= BO1_MAX_RANGE_PCT and breakout_pct >= BO1_BREAK_BUFFER_PCT:
            signals.append(_independent_signal(
                "BO1", sym, ts, px, 1.00, 0.75, "consolidation_breakout",
                prior_range_high=prior_high, prior_range_low=prior_low,
                prior_range_pct=range_pct, breakout_pct=breakout_pct,
            ))
    return signals
