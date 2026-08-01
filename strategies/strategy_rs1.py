"""Self-contained RS1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "RS1"
PAPER_ONLY = True

RS1_MIN_EXCESS_VS_SPY_PCT = 0.75
RS1_MIN_R2 = 0.50
RS1_MIN_RETURN_30M_PCT = 0.75

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
    if len(prices) >= 31 and spy_30m_return_pct is not None and not math.isnan(ret30):
        excess = ret30 - float(spy_30m_return_pct)
        if ret30 >= RS1_MIN_RETURN_30M_PCT and excess >= RS1_MIN_EXCESS_VS_SPY_PCT and r2_30 >= RS1_MIN_R2:
            signals.append(_independent_signal(
                "RS1", sym, ts, px, 0.90, 0.65, "relative_strength",
                return_30m_pct=ret30, spy_return_30m_pct=float(spy_30m_return_pct),
                excess_return_30m_pct=excess, r2_30m=r2_30,
            ))
    return signals
