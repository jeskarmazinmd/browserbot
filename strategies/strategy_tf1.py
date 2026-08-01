"""TF1 trend-pullback research strategy.

This module owns TF1's metadata, thresholds, entry conditions, and payoff
geometry. It is paper-only and does not place broker orders.
"""

import math

STRATEGY_ID = "TF1"
NAME = "Trend Pullback"
VERSION = 1
PAPER_ONLY = True
DESCRIPTION = "Orderly 30-minute uptrend, shallow pullback, then renewed rise."

MIN_RETURN_30M_PCT = 0.75
MIN_R2 = 0.60
PULLBACK_MIN_PCT = 0.25
PULLBACK_MAX_PCT = 0.75
REBOUND_2M_PCT = 0.10
TARGET_PCT = 0.75
STOP_PCT = 0.60


def evaluate_signal(*, symbol, timestamp, prices, current_price, return_30m_pct,
             slope_30m_pct_per_hour, r2_30m, signal_factory,
             simple_return_pct):
    """Return zero or one TF1 signal for the latest completed minute."""
    if len(prices) < 31:
        return []
    if math.isnan(return_30m_pct) or math.isnan(r2_30m):
        return []

    recent_high = float(prices.tail(10).max())
    pullback_pct = (
        (recent_high / float(current_price) - 1.0) * 100.0
        if float(current_price) > 0
        else math.nan
    )
    rebound_2m_pct = simple_return_pct(prices.iloc[-3], prices.iloc[-1])

    qualifies = (
        return_30m_pct >= MIN_RETURN_30M_PCT
        and slope_30m_pct_per_hour > 0
        and r2_30m >= MIN_R2
        and PULLBACK_MIN_PCT <= pullback_pct <= PULLBACK_MAX_PCT
        and rebound_2m_pct >= REBOUND_2M_PCT
    )
    if not qualifies:
        return []

    return [signal_factory(
        STRATEGY_ID,
        symbol,
        timestamp,
        current_price,
        TARGET_PCT,
        STOP_PCT,
        "trend_pullback",
        return_30m_pct=return_30m_pct,
        slope_30m_pct_per_hour=slope_30m_pct_per_hour,
        r2_30m=r2_30m,
        pullback_from_10m_high_pct=pullback_pct,
        rebound_2m_pct=rebound_2m_pct,
    )]


def evaluate(ctx):
    return evaluate_signal(
        symbol=ctx.symbol, timestamp=ctx.timestamp, prices=ctx.prices,
        current_price=ctx.current_price, return_30m_pct=ctx.return_30m_pct,
        slope_30m_pct_per_hour=ctx.slope_30m_pct_per_hour, r2_30m=ctx.r2_30m,
        signal_factory=ctx.signal_factory, simple_return_pct=ctx.simple_return_pct,
    )
