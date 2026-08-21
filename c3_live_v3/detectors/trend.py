import math

import numpy as np

from .common import clean_price_array, return_pct


def detect_trend(values, window=30):
    prices = clean_price_array(values)

    if len(prices) < window + 1:
        return {"detected": False, "reason": "insufficient_history"}

    sample = prices[-(window + 1):]
    returns = np.diff(sample) / sample[:-1]

    x = np.arange(len(sample), dtype=float)
    y = np.log(sample)
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    residual = float(np.sum((y - fitted) ** 2))
    total = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - residual / total if total > 0 else 0.0
    slope_per_minute_pct = (
        math.exp(float(slope)) - 1.0
    ) * 100.0

    up_fraction = (
        float(np.mean(returns > 0))
        if len(returns)
        else math.nan
    )

    nondecreasing = np.diff(sample) >= 0
    higher_low_fraction = (
        float(np.mean(
            (nondecreasing[:-1].astype(float)
             + nondecreasing[1:].astype(float)) / 2.0
        ))
        if len(nondecreasing) >= 2
        else math.nan
    )

    total_return = return_pct(sample[0], sample[-1])

    return {
        "detected": bool(
            total_return > 0
            and slope_per_minute_pct > 0
        ),
        "direction": (
            "up"
            if slope_per_minute_pct > 0
            else "down"
            if slope_per_minute_pct < 0
            else "flat"
        ),
        "window_minutes": window,
        "return_pct": total_return,
        "slope_pct_per_minute": slope_per_minute_pct,
        "slope_pct_per_hour": (
            slope_per_minute_pct * 60.0
            if math.isfinite(slope_per_minute_pct)
            else math.nan
        ),
        "r2": r2,
        "up_minute_fraction": up_fraction,
        "nondecreasing_fraction": higher_low_fraction,
        "distance_from_high_pct": return_pct(
            float(np.max(sample)),
            sample[-1],
        ),
        "distance_from_low_pct": return_pct(
            float(np.min(sample)),
            sample[-1],
        ),
    }
