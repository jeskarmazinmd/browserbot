"""Self-contained OR1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "OR1"
PAPER_ONLY = True

OR1_BREAK_BUFFER_PCT = 0.10
OR1_ENTRY_END_MINUTE_ET = 10 * 60 + 15
OR1_MAX_RANGE_PCT = 2.50
OR1_MIN_RANGE_PCT = 0.20
OR1_RANGE_END_MINUTE_ET = 9 * 60 + 45

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
    if OR1_RANGE_END_MINUTE_ET <= minute_et <= OR1_ENTRY_END_MINUTE_ET:
        opening = work[
            (work["timestamp"].dt.tz_convert(ZoneInfo("America/New_York")).dt.hour == 9)
            & (work["timestamp"].dt.tz_convert(ZoneInfo("America/New_York")).dt.minute >= 30)
            & (work["timestamp"].dt.tz_convert(ZoneInfo("America/New_York")).dt.minute < 45)
        ]
        if len(opening) >= 10:
            or_high = float(opening["price"].max()); or_low = float(opening["price"].min())
            or_range_pct = (or_high / or_low - 1.0) * 100.0 if or_low > 0 else math.nan
            break_pct = (px / or_high - 1.0) * 100.0 if or_high > 0 else math.nan
            if OR1_MIN_RANGE_PCT <= or_range_pct <= OR1_MAX_RANGE_PCT and break_pct >= OR1_BREAK_BUFFER_PCT:
                stop_pct = max(0.50, min(1.00, or_range_pct * 0.50))
                target_pct = max(0.75, min(1.50, or_range_pct))
                signals.append(_independent_signal(
                    "OR1", sym, ts, px, target_pct, stop_pct, "opening_range_breakout",
                    opening_range_high=or_high, opening_range_low=or_low,
                    opening_range_pct=or_range_pct, breakout_pct=break_pct,
                ))
    return signals
