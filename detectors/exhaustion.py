import math

import numpy as np

from .common import clean_price_array, return_pct


def detect_selling_exhaustion(values, window=12):
    prices = clean_price_array(values)

    if len(prices) < window + 1:
        return {"detected": False, "reason": "insufficient_history"}

    sample = prices[-(window + 1):]
    returns = np.diff(sample) / sample[:-1] * 100.0
    half = len(returns) // 2
    early = returns[:half]
    late = returns[half:]

    early_abs = float(np.mean(np.abs(early))) if len(early) else math.nan
    late_abs = float(np.mean(np.abs(late))) if len(late) else math.nan
    contraction = (
        1.0 - late_abs / early_abs
        if early_abs > 0
        else math.nan
    )

    early_negative = early[early < 0]
    late_negative = late[late < 0]
    early_down = (
        float(np.mean(-early_negative))
        if len(early_negative)
        else 0.0
    )
    late_down = (
        float(np.mean(-late_negative))
        if len(late_negative)
        else 0.0
    )
    down_pressure_contraction = (
        1.0 - late_down / early_down
        if early_down > 0
        else math.nan
    )

    low = float(np.min(sample))
    current = float(sample[-1])
    decline = (float(sample[0]) - low) / float(sample[0]) * 100.0
    rebound = return_pct(low, current)

    score_parts = [
        value
        for value in (
            contraction,
            down_pressure_contraction,
            min(rebound / 0.30, 1.0),
        )
        if math.isfinite(value)
    ]
    score = (
        float(np.clip(np.mean(score_parts), 0.0, 1.0))
        if score_parts
        else 0.0
    )

    return {
        "detected": bool(
            decline > 0
            and contraction > 0
            and rebound > 0
        ),
        "decline_to_low_pct": decline,
        "rebound_from_low_pct": rebound,
        "absolute_move_contraction": contraction,
        "down_pressure_contraction": down_pressure_contraction,
        "early_abs_return_pct": early_abs,
        "late_abs_return_pct": late_abs,
        "score": score,
    }
