import math
from .common import clean_prices, return_pct


def detect_mean_reversion(values, baseline_window=30, recent_window=5):
    prices = clean_prices(values)
    if len(prices) < baseline_window + 1:
        return {"detected": False, "reason": "insufficient_history"}
    sample = prices.tail(baseline_window + 1)
    baseline = sample.iloc[:-recent_window] if len(sample) > recent_window else sample.iloc[:-1]
    mean = float(baseline.mean())
    std = float(baseline.std(ddof=0))
    current = float(sample.iloc[-1])
    recent_low = float(sample.tail(recent_window + 1).min())
    z = (current - mean) / std if std > 0 else math.nan
    deviation = return_pct(mean, current)
    rebound = return_pct(recent_low, current)
    drop_to_low = return_pct(float(sample.iloc[0]), recent_low)
    return {
        "detected": bool(math.isfinite(z) and z < 0 and rebound > 0),
        "baseline_mean": mean,
        "baseline_std": std,
        "zscore": z,
        "deviation_from_mean_pct": deviation,
        "drop_to_recent_low_pct": drop_to_low,
        "rebound_from_recent_low_pct": rebound,
        "recent_low_price": recent_low,
    }
