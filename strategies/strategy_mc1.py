"""Self-contained MC1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "MC1"
PAPER_ONLY = True

MC1_MAX_DISTANCE_FROM_10M_HIGH_PCT = 0.35
MC1_MIN_R2_30M = 0.55
MC1_MIN_RETURN_15M_PCT = 0.80
MC1_MIN_RETURN_5M_PCT = 0.25
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
    if len(prices) >= 31:
        ret15 = _simple_return_pct(prices.iloc[-16], prices.iloc[-1])
        ret5 = _simple_return_pct(prices.iloc[-6], prices.iloc[-1])
        high10 = float(prices.tail(10).max())
        distance_high = (high10 / px - 1.0) * 100.0 if px > 0 else math.nan
        if (ret15 >= MC1_MIN_RETURN_15M_PCT and ret5 >= MC1_MIN_RETURN_5M_PCT
                and r2_30 >= MC1_MIN_R2_30M
                and distance_high <= MC1_MAX_DISTANCE_FROM_10M_HIGH_PCT):
            signals.append(_independent_signal(
                "MC1", sym, ts, px, 0.80, 0.55, "momentum_continuation",
                return_15m_pct=ret15, return_5m_pct=ret5, r2_30m=r2_30,
                distance_from_10m_high_pct=distance_high,
                forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))
    return signals
