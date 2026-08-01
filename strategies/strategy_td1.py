"""Self-contained TD1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "TD1"
PAPER_ONLY = True

NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"
TD1_END_MINUTE_ET = 11 * 60 + 30
TD1_MIN_EXCESS_VS_SPY_PCT = 0.50
TD1_MIN_RETURN_30M_PCT = 0.60
TD1_START_MINUTE_ET = 10 * 60

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
    if (TD1_START_MINUTE_ET <= minute_et <= TD1_END_MINUTE_ET
            and len(prices) >= 31 and spy_30m_return_pct is not None):
        excess = ret30 - float(spy_30m_return_pct)
        ret5 = _simple_return_pct(prices.iloc[-6], prices.iloc[-1])
        if ret30 >= TD1_MIN_RETURN_30M_PCT and excess >= TD1_MIN_EXCESS_VS_SPY_PCT and ret5 > 0:
            signals.append(_independent_signal(
                "TD1", sym, ts, px, 0.75, 0.55, "time_of_day_relative_strength",
                minute_et=minute_et, return_30m_pct=ret30,
                spy_return_30m_pct=float(spy_30m_return_pct), excess_return_30m_pct=excess,
                return_5m_pct=ret5, forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))
    return signals
