"""Self-contained HL1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "HL1"
PAPER_ONLY = True

HL1_BREAK_BUFFER_PCT = 0.10
HL1_MIN_HIGHER_LOW_PCT = 0.15
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
    if len(prices) >= 21:
        w = prices.tail(21).reset_index(drop=True)
        local_lows = [i for i in range(1, len(w)-1) if w.iloc[i] <= w.iloc[i-1] and w.iloc[i] < w.iloc[i+1]]
        if len(local_lows) >= 2:
            i1, i2 = local_lows[-2], local_lows[-1]
            if i2 - i1 >= 3:
                low1, low2 = float(w.iloc[i1]), float(w.iloc[i2])
                higher_low_pct = (low2 / low1 - 1.0) * 100.0 if low1 > 0 else math.nan
                intervening_high = float(w.iloc[i1:i2+1].max())
                break_pct = (px / intervening_high - 1.0) * 100.0 if intervening_high > 0 else math.nan
                if higher_low_pct >= HL1_MIN_HIGHER_LOW_PCT and break_pct >= HL1_BREAK_BUFFER_PCT:
                    signals.append(_independent_signal(
                        "HL1", sym, ts, px, 0.80, 0.55, "higher_low_breakout",
                        first_low=low1, second_low=low2, higher_low_pct=higher_low_pct,
                        intervening_high=intervening_high, breakout_pct=break_pct,
                        forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
                    ))
    return signals
