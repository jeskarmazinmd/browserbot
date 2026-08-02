import math

import numpy as np

from .common import clean_price_array, return_pct


def detect_mean_reversion(
    values,
    baseline_window=30,
    recent_window=5,
):
    prices = clean_price_array(values)

    if len(prices) < baseline_window + 1:
        return {"detected": False, "reason": "insufficient_history"}

    sample = prices[-(baseline_window + 1):]
    baseline = (
        sample[:-recent_window]
        if len(sample) > recent_window
        else sample[:-1]
    )

    mean = float(np.mean(baseline))
    std = float(np.std(baseline, ddof=0))
    current = float(sample[-1])
    recent_low = float(np.min(sample[-(recent_window + 1):]))
    zscore = (
        (current - mean) / std
        if std > 0
        else math.nan
    )
    deviation = return_pct(mean, current)
    rebound = return_pct(recent_low, current)
    drop_to_low = return_pct(float(sample[0]), recent_low)

    return {
        "detected": bool(
            math.isfinite(zscore)
            and zscore < 0
            and rebound > 0
        ),
        "baseline_mean": mean,
        "baseline_std": std,
        "zscore": zscore,
        "deviation_from_mean_pct": deviation,
        "drop_to_recent_low_pct": drop_to_low,
        "rebound_from_recent_low_pct": rebound,
        "recent_low_price": recent_low,
    }
