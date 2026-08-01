"""Self-contained VE1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "VE1"
PAPER_ONLY = True

VE1_BREAK_BUFFER_PCT = 0.10
VE1_COMPRESSION_MINUTES = 15
VE1_MAX_COMPRESSION_RANGE_PCT = 0.60

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
    if len(prices) >= VE1_COMPRESSION_MINUTES + 2:
        compressed = prices.iloc[-(VE1_COMPRESSION_MINUTES + 1):-1]
        c_high = float(compressed.max()); c_low = float(compressed.min())
        c_range_pct = (c_high / c_low - 1.0) * 100.0 if c_low > 0 else math.nan
        expansion_pct = (px / c_high - 1.0) * 100.0 if c_high > 0 else math.nan
        if c_range_pct <= VE1_MAX_COMPRESSION_RANGE_PCT and expansion_pct >= VE1_BREAK_BUFFER_PCT:
            target_pct = max(0.60, min(1.20, c_range_pct * 1.5))
            signals.append(_independent_signal(
                "VE1", sym, ts, px, target_pct, 0.60, "volatility_expansion",
                compression_range_high=c_high, compression_range_low=c_low,
                compression_range_pct=c_range_pct, expansion_pct=expansion_pct,
            ))
    return signals
