import math
from .common import clean_prices, return_pct


def detect_pullback(values, trend_window=30, recent_window=8):
    prices = clean_prices(values)
    needed = max(trend_window + 1, recent_window + 2)
    if len(prices) < needed:
        return {"detected": False, "reason": "insufficient_history"}
    sample = prices.tail(trend_window + 1)
    peak_pos = int(sample.to_numpy().argmax())
    peak = float(sample.iloc[peak_pos])
    start = float(sample.iloc[0])
    current = float(sample.iloc[-1])
    after_peak = sample.iloc[peak_pos:]
    low = float(after_peak.min())
    low_pos = peak_pos + int(after_peak.to_numpy().argmin())
    prior_move = return_pct(start, peak)
    depth = (peak - low) / peak * 100.0 if peak > 0 else math.nan
    recovery = return_pct(low, current)
    retracement_fraction = depth / prior_move if prior_move > 0 else math.nan
    return {
        "detected": bool(prior_move > 0 and depth > 0 and low_pos < len(sample) - 1 and recovery > 0),
        "prior_move_pct": prior_move,
        "pullback_depth_pct": depth,
        "retracement_fraction": retracement_fraction,
        "recovery_from_low_pct": recovery,
        "minutes_since_peak": len(sample) - 1 - peak_pos,
        "minutes_since_low": len(sample) - 1 - low_pos,
        "peak_price": peak,
        "pullback_low_price": low,
        "current_price": current,
    }
