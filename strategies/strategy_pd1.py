"""Self-contained PD1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "PD1"
PAPER_ONLY = True

NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"
PD1_MIN_ONE_MINUTE_DROP_PCT = 1.00
PD1_MIN_REBOUND_FROM_LOW_PCT = 0.40

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
    if len(prices) >= 12:
        w = prices.tail(12).reset_index(drop=True)
        minute_returns = w.pct_change().dropna() * 100.0
        worst_pos = int(minute_returns.idxmin())
        worst_drop = -float(minute_returns.loc[worst_pos])
        low_after = float(w.iloc[worst_pos:].min())
        low_pos = int(w.iloc[worst_pos:].idxmin())
        low_age = (len(w) - 1) - low_pos
        rebound_low = (px / low_after - 1.0) * 100.0 if low_after > 0 else math.nan
        rebound2 = _simple_return_pct(w.iloc[-3], w.iloc[-1])
        if (worst_drop >= PD1_MIN_ONE_MINUTE_DROP_PCT and 2 <= low_age <= 8
                and rebound_low >= PD1_MIN_REBOUND_FROM_LOW_PCT and rebound2 > 0):
            signals.append(_independent_signal(
                "PD1", sym, ts, px, 0.85, 0.70, "panic_drop_snapback",
                worst_one_minute_drop_pct=worst_drop, low_age_minutes=low_age,
                rebound_from_low_pct=rebound_low, rebound_2m_pct=rebound2,
                forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))
    return signals
