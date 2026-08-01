"""Self-contained EMA2 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "EMA2"
PAPER_ONLY = True

EMA2_MAX_PULLBACK_DISTANCE_PCT = 0.35
EMA2_MIN_BOUNCE_2M_PCT = 0.10
EMA2_SPAN = 20
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
    if len(prices) >= EMA2_SPAN + 4:
        ema20 = _ema(prices, EMA2_SPAN)
        ema_rising = float(ema20.iloc[-1]) > float(ema20.iloc[-4])
        prior_distance = abs(float(prices.iloc[-2]) / float(ema20.iloc[-2]) - 1.0) * 100.0
        bounce2 = _simple_return_pct(prices.iloc[-3], prices.iloc[-1])
        reclaimed = float(prices.iloc[-2]) <= float(ema20.iloc[-2]) and px > float(ema20.iloc[-1])
        if (
            ema_rising
            and prior_distance <= EMA2_MAX_PULLBACK_DISTANCE_PCT
            and bounce2 >= EMA2_MIN_BOUNCE_2M_PCT
            and reclaimed
        ):
            signals.append(_independent_signal(
                "EMA2", sym, ts, px, 0.75, 0.50, "rising_ema20_pullback_bounce",
                ema_20=float(ema20.iloc[-1]),
                ema_20_change_3m_pct=_simple_return_pct(ema20.iloc[-4], ema20.iloc[-1]),
                prior_distance_from_ema_pct=prior_distance,
                rebound_2m_pct=bounce2,
                forward_start_utc=EMA_RESEARCH_FORWARD_START_UTC,
            ))
    return signals
