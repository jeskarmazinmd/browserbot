"""Self-contained SMA1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "SMA1"
PAPER_ONLY = True

EMA_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"
SMA1_CONFIRM_MINUTES = 2
SMA1_FAST_WINDOW = 20
SMA1_SLOW_WINDOW = 50

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
    if len(prices) >= SMA1_SLOW_WINDOW + SMA1_CONFIRM_MINUTES + 1:
        sma20 = prices.rolling(SMA1_FAST_WINDOW).mean()
        sma50 = prices.rolling(SMA1_SLOW_WINDOW).mean()
        confirmed = (
            float(sma20.iloc[-3]) <= float(sma50.iloc[-3])
            and float(sma20.iloc[-2]) > float(sma50.iloc[-2])
            and float(sma20.iloc[-1]) > float(sma50.iloc[-1])
        )
        if confirmed:
            signals.append(_independent_signal(
                "SMA1", sym, ts, px, 0.85, 0.60, "sma_20_50_bullish_crossover",
                sma_20=float(sma20.iloc[-1]), sma_50=float(sma50.iloc[-1]),
                confirmation_minutes=SMA1_CONFIRM_MINUTES,
                forward_start_utc=EMA_RESEARCH_FORWARD_START_UTC,
            ))
    return signals
