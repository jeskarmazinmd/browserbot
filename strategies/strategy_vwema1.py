"""Self-contained VWEMA1 strategy module.

Extracted without intentional behavior changes from live_strategy_runner.py.
"""
import math
import numpy as np
import pandas as pd
from zoneinfo import ZoneInfo

STRATEGY_ID = "VWEMA1"
PAPER_ONLY = True

EMA_RESEARCH_FORWARD_START_UTC = "2026-08-03T13:30:00+00:00"
VWEMA1_EMA_SPAN = 20
VWEMA1_MIN_PRICE_ABOVE_VWAP_PCT = 0.05
VWEMA1_MIN_RETURN_15M_PCT = 0.30

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
        ema20 = _ema(prices, VWEMA1_EMA_SPAN)
        vwap_proxy = float(prices.tail(30).mean())
        above_proxy_pct = (px / vwap_proxy - 1.0) * 100.0 if vwap_proxy > 0 else math.nan
        ret15 = _simple_return_pct(prices.iloc[-16], prices.iloc[-1])
        if (
            px > float(ema20.iloc[-1])
            and above_proxy_pct >= VWEMA1_MIN_PRICE_ABOVE_VWAP_PCT
            and ret15 >= VWEMA1_MIN_RETURN_15M_PCT
            and float(ema20.iloc[-1]) > float(ema20.iloc[-4])
        ):
            signals.append(_independent_signal(
                "VWEMA1", sym, ts, px, 0.80, 0.55, "price_above_mean_proxy_and_ema20",
                ema_20=float(ema20.iloc[-1]), rolling_price_mean_30m=vwap_proxy,
                distance_above_price_mean_pct=above_proxy_pct,
                return_15m_pct=ret15,
                proxy_note="rolling price mean; not true volume-weighted VWAP",
                forward_start_utc=EMA_RESEARCH_FORWARD_START_UTC,
            ))

    return signals
