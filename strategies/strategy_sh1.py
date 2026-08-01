"""Self-contained SH1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "SH1"
PAPER_ONLY = True

NEW_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"
SH1_MIN_DECLINE_20M_PCT = 1.00
SH1_MIN_FLATTENING_RATIO = 0.50

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
        decline20 = (float(w.iloc[0]) / float(w.min()) - 1.0) * 100.0
        first_half = _simple_return_pct(w.iloc[0], w.iloc[10])
        second_half = _simple_return_pct(w.iloc[10], w.iloc[-1])
        rebound3 = _simple_return_pct(w.iloc[-4], w.iloc[-1])
        flattening = abs(second_half) / abs(first_half) if first_half < 0 else math.inf
        if decline20 >= SH1_MIN_DECLINE_20M_PCT and first_half < 0 and flattening <= SH1_MIN_FLATTENING_RATIO and rebound3 > 0:
            signals.append(_independent_signal(
                "SH1", sym, ts, px, 0.70, 0.60, "decline_shape_flattening",
                decline_20m_pct=decline20, first_half_return_pct=first_half,
                second_half_return_pct=second_half, flattening_ratio=flattening,
                rebound_3m_pct=rebound3, forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))
    return signals
