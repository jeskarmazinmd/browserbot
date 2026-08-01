"""Self-contained TL1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "TL1"
PAPER_ONLY = True

NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"
TL1_MIN_PRIOR_GAP_BELOW_TREND_PCT = 0.25
TL1_MIN_R2_30M = 0.45

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
        y = np.log(prices.tail(31).to_numpy(dtype=float))
        x = np.arange(len(y), dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        trend = np.exp(intercept + slope * x)
        prior_gap = (trend[-2] / float(prices.iloc[-2]) - 1.0) * 100.0
        crossed = float(prices.iloc[-2]) < trend[-2] and px >= trend[-1]
        if slope > 0 and r2_30 >= TL1_MIN_R2_30M and prior_gap >= TL1_MIN_PRIOR_GAP_BELOW_TREND_PCT and crossed:
            signals.append(_independent_signal(
                "TL1", sym, ts, px, 0.75, 0.50, "uptrend_line_reclaim",
                r2_30m=r2_30, slope_30m_pct_per_hour=slope30,
                prior_gap_below_trendline_pct=prior_gap,
                trendline_price_now=float(trend[-1]),
                forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))
    return signals
