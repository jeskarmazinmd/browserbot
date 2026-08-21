import math

import numpy as np

from .common import clean_price_array, return_pct


def detect_support_rejection(
    values,
    window=20,
    tolerance_pct=0.20,
):
    prices = clean_price_array(values)

    if len(prices) < window:
        return {"detected": False, "reason": "insufficient_history"}

    sample = prices[-window:]
    local_lows = [
        index
        for index in range(1, len(sample) - 1)
        if (
            sample[index] <= sample[index - 1]
            and sample[index] <= sample[index + 1]
        )
    ]

    if len(local_lows) < 2:
        return {"detected": False, "reason": "fewer_than_two_tests"}

    first_index, second_index = local_lows[-2:]
    first = float(sample[first_index])
    second = float(sample[second_index])
    level = min(first, second)
    test_gap_pct = (
        abs(second / first - 1.0) * 100.0
        if first > 0
        else math.nan
    )
    current = float(sample[-1])
    confirmation = return_pct(level, current)
    between_high = float(
        np.max(sample[first_index:second_index + 1])
    )
    separation = return_pct(level, between_high)

    return {
        "detected": bool(
            test_gap_pct <= tolerance_pct
            and second_index < len(sample) - 1
            and confirmation > 0
        ),
        "support_price": level,
        "first_test_price": first,
        "second_test_price": second,
        "test_gap_pct": test_gap_pct,
        "minutes_between_tests": second_index - first_index,
        "separation_bounce_pct": separation,
        "confirmation_from_support_pct": confirmation,
        "minutes_since_second_test": (
            len(sample) - 1 - second_index
        ),
    }
