import math
from .common import clean_prices, linear_trend, return_pct


def detect_trend(values, window=30):
    prices = clean_prices(values)
    if len(prices) < window + 1:
        return {"detected": False, "reason": "insufficient_history"}
    sample = prices.tail(window + 1)
    returns = sample.pct_change().dropna()
    slope_per_minute_pct, r2 = linear_trend(sample)
    up_fraction = float((returns > 0).mean()) if len(returns) else math.nan
    higher_low_fraction = float((sample.diff().dropna() >= 0).rolling(2).mean().dropna().mean()) if len(sample) >= 4 else math.nan
    total_return = return_pct(sample.iloc[0], sample.iloc[-1])
    return {
        "detected": bool(total_return > 0 and slope_per_minute_pct > 0),
        "direction": "up" if slope_per_minute_pct > 0 else "down" if slope_per_minute_pct < 0 else "flat",
        "window_minutes": window,
        "return_pct": total_return,
        "slope_pct_per_minute": slope_per_minute_pct,
        "slope_pct_per_hour": slope_per_minute_pct * 60.0 if math.isfinite(slope_per_minute_pct) else math.nan,
        "r2": r2,
        "up_minute_fraction": up_fraction,
        "nondecreasing_fraction": higher_low_fraction,
        "distance_from_high_pct": return_pct(float(sample.max()), sample.iloc[-1]),
        "distance_from_low_pct": return_pct(float(sample.min()), sample.iloc[-1]),
    }
