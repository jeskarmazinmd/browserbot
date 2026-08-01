"""Self-contained EMA1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "EMA1"
PAPER_ONLY = True

EMA1_FAST_SPAN = 9
EMA1_MIN_VOLUME_RATIO = 1.20
EMA1_SLOW_SPAN = 21
EMA_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"

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
    if len(prices) >= EMA1_SLOW_SPAN + 3:
        fast = _ema(prices, EMA1_FAST_SPAN)
        slow = _ema(prices, EMA1_SLOW_SPAN)
        crossed_now = float(fast.iloc[-2]) <= float(slow.iloc[-2]) and float(fast.iloc[-1]) > float(slow.iloc[-1])
        if crossed_now:
            volume_ratio = _confirm_recent_volume_ratio(sym)
            if volume_ratio is not None and volume_ratio >= EMA1_MIN_VOLUME_RATIO:
                signals.append(_independent_signal(
                    "EMA1", sym, ts, px, 0.75, 0.55, "ema_9_21_bullish_crossover",
                    ema_9=float(fast.iloc[-1]), ema_21=float(slow.iloc[-1]),
                    prior_ema_9=float(fast.iloc[-2]), prior_ema_21=float(slow.iloc[-2]),
                    latest_volume_ratio=volume_ratio,
                    minimum_volume_ratio=EMA1_MIN_VOLUME_RATIO,
                    forward_start_utc=EMA_RESEARCH_FORWARD_START_UTC,
                ))
    return signals
