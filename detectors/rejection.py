import math
import numpy as np
from .common import clean_prices, return_pct


def detect_support_rejection(values, window=20, tolerance_pct=0.20):
    prices = clean_prices(values)
    if len(prices) < window:
        return {"detected": False, "reason": "insufficient_history"}
    sample = prices.tail(window).reset_index(drop=True)
    arr = sample.to_numpy()
    local_lows = [i for i in range(1, len(arr)-1) if arr[i] <= arr[i-1] and arr[i] <= arr[i+1]]
    if len(local_lows) < 2:
        return {"detected": False, "reason": "fewer_than_two_tests"}
    first_i, second_i = local_lows[-2], local_lows[-1]
    first, second = float(arr[first_i]), float(arr[second_i])
    level = min(first, second)
    test_gap_pct = abs(second / first - 1.0) * 100.0 if first > 0 else math.nan
    current = float(arr[-1])
    confirmation = return_pct(level, current)
    between_high = float(np.max(arr[first_i:second_i+1]))
    separation = return_pct(level, between_high)
    return {
        "detected": bool(test_gap_pct <= tolerance_pct and second_i < len(arr)-1 and confirmation > 0),
        "support_price": level,
        "first_test_price": first,
        "second_test_price": second,
        "test_gap_pct": test_gap_pct,
        "minutes_between_tests": second_i - first_i,
        "separation_bounce_pct": separation,
        "confirmation_from_support_pct": confirmation,
        "minutes_since_second_test": len(arr)-1-second_i,
    }
