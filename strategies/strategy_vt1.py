"""Self-contained VT1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "VT1"
PAPER_ONLY = True

NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"
VT1_MAX_CONFLUENCE_DISTANCE_PCT = 0.20
VT1_MIN_R2_45M = 0.45
VT1_MIN_REBOUND_2M_PCT = 0.10

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
    if len(prices) >= 46:
        w45 = prices.tail(46)
        slope45, r2_45 = fit_log_slope_pct_per_hour(w45)
        y45 = np.log(w45.to_numpy(dtype=float)); x45 = np.arange(len(y45), dtype=float)
        s45, i45 = np.polyfit(x45, y45, 1)
        trend_now = float(np.exp(i45 + s45 * x45[-1]))
        mean30 = float(prices.tail(30).mean())
        trend_dist = abs(px / trend_now - 1.0) * 100.0
        mean_dist = abs(px / mean30 - 1.0) * 100.0
        rebound2 = _simple_return_pct(prices.iloc[-3], prices.iloc[-1])
        if (slope45 > 0 and r2_45 >= VT1_MIN_R2_45M
                and trend_dist <= VT1_MAX_CONFLUENCE_DISTANCE_PCT
                and mean_dist <= VT1_MAX_CONFLUENCE_DISTANCE_PCT
                and rebound2 >= VT1_MIN_REBOUND_2M_PCT):
            signals.append(_independent_signal(
                "VT1", sym, ts, px, 0.80, 0.55, "trendline_mean_confluence",
                slope_45m_pct_per_hour=slope45, r2_45m=r2_45,
                trendline_price=trend_now, rolling_mean_30m=mean30,
                distance_to_trendline_pct=trend_dist, distance_to_mean_pct=mean_dist,
                rebound_2m_pct=rebound2, forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))
    return signals
