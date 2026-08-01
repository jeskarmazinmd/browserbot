"""Self-contained VR1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "VR1"
PAPER_ONLY = True

VR1_HOLD_MINUTES = 2
VR1_MIN_DEPTH_BELOW_VWAP_PCT = 0.40

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
    if len(prices) >= 31:
        rolling = prices.tail(31)
        proxy = float(rolling.iloc[:-2].mean())
        historical_low = float(rolling.iloc[:-2].min())
        depth_pct = (proxy / historical_low - 1.0) * 100.0 if historical_low > 0 else math.nan
        held_above = float(rolling.iloc[-2]) >= proxy and float(rolling.iloc[-1]) >= proxy
        crossed = float(rolling.iloc[-3]) < proxy <= float(rolling.iloc[-2])
        if depth_pct >= VR1_MIN_DEPTH_BELOW_VWAP_PCT and crossed and held_above:
            signals.append(_independent_signal(
                "VR1", sym, ts, px, 0.75, 0.45, "rolling_mean_reclaim_proxy",
                rolling_mean_30m=proxy, prior_depth_below_proxy_pct=depth_pct,
                confirmation_minutes=VR1_HOLD_MINUTES,
            ))
    return signals
