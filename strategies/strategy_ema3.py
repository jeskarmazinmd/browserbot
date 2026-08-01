"""Self-contained EMA3 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "EMA3"
PAPER_ONLY = True

EMA3_ALIGNMENT_MINUTES = 5
EMA3_BREAKOUT_LOOKBACK_MINUTES = 10
EMA3_BREAK_BUFFER_PCT = 0.05
EMA3_FAST_SPAN = 9
EMA3_MID_SPAN = 21
EMA3_SLOW_SPAN = 50
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
    if len(prices) >= EMA3_SLOW_SPAN + EMA3_ALIGNMENT_MINUTES + 2:
        ema9 = _ema(prices, EMA3_FAST_SPAN)
        ema21 = _ema(prices, EMA3_MID_SPAN)
        ema50 = _ema(prices, EMA3_SLOW_SPAN)
        aligned = (
            (ema9.tail(EMA3_ALIGNMENT_MINUTES) > ema21.tail(EMA3_ALIGNMENT_MINUTES)).all()
            and (ema21.tail(EMA3_ALIGNMENT_MINUTES) > ema50.tail(EMA3_ALIGNMENT_MINUTES)).all()
        )
        prior_high = float(prices.iloc[-(EMA3_BREAKOUT_LOOKBACK_MINUTES + 1):-1].max())
        breakout_pct = (px / prior_high - 1.0) * 100.0 if prior_high > 0 else math.nan
        if aligned and breakout_pct >= EMA3_BREAK_BUFFER_PCT:
            signals.append(_independent_signal(
                "EMA3", sym, ts, px, 0.90, 0.60, "ema_alignment_breakout",
                ema_9=float(ema9.iloc[-1]), ema_21=float(ema21.iloc[-1]), ema_50=float(ema50.iloc[-1]),
                alignment_minutes=EMA3_ALIGNMENT_MINUTES,
                prior_high=prior_high, breakout_pct=breakout_pct,
                forward_start_utc=EMA_RESEARCH_FORWARD_START_UTC,
            ))
    return signals
