"""Self-contained AV1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "AV1"
PAPER_ONLY = True

AV1_MIN_DRAWDOWN_PCT = 0.40
AV1_MIN_REBOUND_2M_PCT = 0.10
AV1_VOLATILITY_MULTIPLIER = 2.0
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
        returns_1m = prices.tail(31).pct_change().dropna() * 100.0
        sigma = float(returns_1m.std(ddof=0)) if len(returns_1m) >= 10 else math.nan
        high15 = float(prices.tail(16).max())
        low5 = float(prices.tail(6).min())
        drawdown = (high15 / low5 - 1.0) * 100.0 if low5 > 0 else math.nan
        rebound2 = _simple_return_pct(prices.iloc[-3], prices.iloc[-1])
        required_drawdown = max(AV1_MIN_DRAWDOWN_PCT, AV1_VOLATILITY_MULTIPLIER * sigma) if not math.isnan(sigma) else math.inf
        required_rebound = max(AV1_MIN_REBOUND_2M_PCT, 0.5 * sigma) if not math.isnan(sigma) else math.inf
        if slope30 > 0 and drawdown >= required_drawdown and rebound2 >= required_rebound:
            signals.append(_independent_signal(
                "AV1", sym, ts, px, 0.75, 0.60, "volatility_adaptive_rebound",
                recent_sigma_1m_pct=sigma, drawdown_15m_to_5m_low_pct=drawdown,
                required_drawdown_pct=required_drawdown, rebound_2m_pct=rebound2,
                required_rebound_pct=required_rebound,
                forward_start_utc=NEW_RESEARCH_FORWARD_START_UTC,
            ))
    return signals
